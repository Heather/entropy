# -*- coding: utf-8 -*-
"""

    @author: Fabio Erculiani <lxnay@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Fabio Erculiani
    @license: GPL-2

    B{Entropy Framework cache module}.

    This module contains the Entropy, asynchronous caching logic.
    It is not meant to handle cache pollution management, because
    this is either handled implicitly when cached items are pulled
    in or by using entropy.dump or cache cleaners (see
    entropy.client.interfaces.cache mixin methods)

"""
import os
import sys
from entropy.const import etpConst
from entropy.core import Singleton
from entropy.misc import TimeScheduled, Lifo
import time

import entropy.dump
import entropy.tools

class EntropyCacher(Singleton):
    """
        Entropy asynchronous and synchronous cache writer
        and reader. This class is a Singleton and contains
        a thread doing the cache writes asynchronously, thus
        it must be stopped before your application is terminated
        calling the stop() method.

        Sample code:

            >>> # import module
            >>> from entropy.cache import EntropyCacher
            ...
            >>> # first EntropyCacher load, start it
            >>> cacher = EntropyCacher()
            >>> cacher.start()
            ...
            >>> # now store something into its cache
            >>> cacher.push('my_identifier1', [1, 2, 3])
            >>> # now store something synchronously
            >>> cacher.push('my_identifier2', [1, 2, 3], async = False)
            ...
            >>> # now flush all the caches to disk, and make sure all
            >>> # is written
            >>> cacher.sync(wait = True)
            ...
            >>> # now fetch something from the cache
            >>> data = cacher.pop('my_identifier1')
            [1, 2, 3]
            ...
            >>> # now discard all the cached (async) writes
            >>> cacher.discard()
            ...
            >>> # and stop EntropyCacher
            >>> cacher.stop()

    """

    def init_singleton(self):
        """
        Singleton overloaded method. Equals to __init__.
        This is the place where all the properties initialization
        takes place.
        """
        import threading
        import copy
        self.__copy = copy
        self.__alive = False
        self.__cache_writer = None
        self.__cache_buffer = Lifo()
        self.__cache_lock = threading.Lock()

    def __copy_obj(self, obj):
        """
        Return a copy of an object done by the standard
        library "copy" module.

        @param obj: object to copy
        @type obj: any Python object
        @rtype: copied object
        @return: copied object
        """
        return self.__copy.deepcopy(obj)

    def __cacher(self):
        """
        This is where the actual asynchronous copy takes
        place. __cacher runs on a different threads and
        all the operations done by this are atomic and
        thread-safe. It just loops over and over until
        __alive becomes False.
        """
        while True:
            if not self.__alive:
                break
            with self.__cache_lock:
                try:
                    data = self.__cache_buffer.pop()
                except (ValueError, TypeError,):
                    # TypeError is when objects are being destroyed
                    break # stack empty
            key, data = data
            d_o = entropy.dump.dumpobj
            if not d_o:
                break
            d_o(key, data)

    def __del__(self):
        self.stop()

    def start(self):
        """
        This is the method used to start the asynchronous cache
        writer but also the whole cacher. If this method is not
        called, the instance will always trash and cache write
        request.

        @return: None
        """
        with self.__cache_lock:
            self.__cache_buffer.clear()
        self.__cache_writer = TimeScheduled(1, self.__cacher)
        self.__cache_writer.set_delay_before(True)
        self.__cache_writer.start()
        while not self.__cache_writer.isAlive():
            continue
        self.__alive = True

    def is_started(self):
        """
        Return whether start is called or not. This equals to
        checking if the cacher is running, thus is writing cache
        to disk.

        @return: None
        """
        return self.__alive

    def stop(self):
        """
        This method stops the execution of the cacher, which won't
        accept cache writes anymore. The thread responsible of writing
        to disk is stopped here and the Cacher will be back to being
        inactive. A watchdog will avoid the thread to freeze the
        call if the write buffer is overloaded.

        @return: None
        """

        watch_dog = 80
        while self.__cache_buffer.is_filled() and (watch_dog > 0):
            watch_dog -= 1
            time.sleep(0.125)
        self.__alive = False

        with self.__cache_lock:
            self.__cache_buffer.clear()
        if self.__cache_writer != None:
            self.__cache_writer.kill()
            self.__cache_writer.join()
            self.__cache_writer = None

    def sync(self, wait = False):
        """
        This method can be called anytime and forces the instance
        to flush all the cache writes queued to disk. If wait == False
        a watchdog prevents this call to get stuck in case of write
        buffer overloads.

        @keyword wait: indicates if waiting until done (synchronous mode) or not
        @type wait: bool
        @rtype: None
        @return: None
        """
        if not self.__alive:
            self.__cache_buffer.clear()
            return

        watch_dog = 40
        while self.__cache_buffer.is_filled() and ((watch_dog > 0) or wait) \
            and self.__alive:

            if not wait:
                watch_dog -= 1
            time.sleep(0.125)

        self.__cache_buffer.clear()

    def discard(self):
        """
        This method makes buffered cache to be discarded synchronously.

        @return: None
        """
        self.__cache_buffer.clear()
        with self.__cache_lock:
            self.__cache_buffer.clear() # make sure twice

    def push(self, key, data, async = True):
        """
        This is the place where data is either added
        to the write queue or written to disk (if async == False)
        only and only if start() method has been called.

        @param key: cache data identifier
        @type key: string
        @param data: picklable object
        @type data: any picklable object
        @keyword async: store cache asynchronously or not
        @type async: bool
        @rtype: None
        @return: None
        """
        if not self.__alive:
            return
        if async:
            with self.__cache_lock:
                try:
                    self.__cache_buffer.push((key, self.__copy_obj(data),))
                except TypeError:
                    # sometimes, very rarely, copy.deepcopy() is unable
                    # to properly copy an object (blame Python bug)
                    sys.stdout.write("!!! cannot cache object with key %s\n" % (
                        key,))
                    sys.stdout.flush()
        else:
            entropy.dump.dumpobj(key, data)

    def pop(self, key):
        """
        This is the place where data is retrieved from cache.
        You must know the cache identifier used when push()
        was called.

        @param key: cache data identifier
        @type key: string
        @rtype: Python object
        @return: object stored into the stack or None (if stack is empty)
        """
        with self.__cache_lock:
            l_o = entropy.dump.loadobj
            if not l_o:
                return
            return l_o(key)

    @staticmethod
    def clear_cache_item(cache_item):
        """
        Clear Entropy Cache item from on-disk cache.

        @param cache_item: Entropy Cache item identifier
        @type cache_item: string
        """
        dump_path = os.path.join(etpConst['dumpstoragedir'], cache_item)
        dump_dir = os.path.dirname(dump_path)
        for currentdir, subdirs, files in os.walk(dump_dir):
            path = os.path.join(dump_dir, currentdir)
            for item in files:
                if item.endswith(etpConst['cachedumpext']):
                    item = os.path.join(path, item)
                    try:
                        os.remove(item)
                    except (OSError, IOError,):
                        pass
            try:
                if not os.listdir(path):
                    os.rmdir(path)
            except (OSError, IOError,):
                pass
