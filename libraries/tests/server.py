# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')
sys.path.insert(0, '../')
import unittest
import os
import shutil
from entropy.server.interfaces import Server
from entropy.const import etpConst
from entropy.core.settings.base import SystemSettings
from entropy.db import EntropyRepository
from entropy.exceptions import RepositoryError
import tests._misc as _misc

class EntropyRepositoryTest(unittest.TestCase):

    def setUp(self):
        sys.stdout.write("%s called\n" % (self,))
        sys.stdout.flush()
        self.default_repo = "foo"
        etpConst['defaultserverrepositoryid'] = self.default_repo
        etpConst['uid'] = 0
        self.SystemSettings = SystemSettings()

        # create fake server repo
        self.Server = Server(fake_default_repo_id = self.default_repo,
            fake_default_repo_desc = 'foo desc', fake_default_repo = True)


    def tearDown(self):
        """
        tearDown is run after each test
        """
        sys.stdout.write("%s ran\n" % (self,))
        sys.stdout.flush()
        self.Server.destroy()

    def test_server_instance(self):
        self.assertEqual(self.default_repo, self.Server.default_repository)

    def test_server_repo(self):
        dbconn = self.Server.open_server_repository()
        self.assertEqual(':memory:', dbconn.dbFile)

    def test_package_injection(self):
        test_pkg = _misc.get_test_entropy_package()
        tmp_test_pkg = test_pkg+".tmp"
        shutil.copy2(test_pkg, tmp_test_pkg)
        added = self.Server.add_packages_to_repository([(tmp_test_pkg, False,)],
            ask = False)
        self.assertEqual(set([1]), added)
        def do_stat():
            os.stat(tmp_test_pkg)
        self.assertRaises(OSError, do_stat)
        dbconn = self.Server.open_server_repository()
        self.assertNotEqual(None, dbconn.retrieveAtom(1))

if __name__ == '__main__':
    if "--debug" in sys.argv:
        sys.argv.remove("--debug")
        from entropy.const import etpUi
        etpUi['debug'] = True
    unittest.main()
