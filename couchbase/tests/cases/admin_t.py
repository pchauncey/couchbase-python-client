#
# Copyright 2013, Couchbase, Inc.
# All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License")
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import sys
import os

from couchbase.admin import Admin
from couchbase.bucket import Bucket
from couchbase.result import HttpResult
from couchbase.connstr import ConnectionString
from couchbase.exceptions import (
    ArgumentError, AuthError, CouchbaseError,
    CouchbaseNetworkError, HTTPError)
from couchbase.tests.base import CouchbaseTestCase, SkipTest
from couchbase.auth_domain import AuthDomain


class AdminSimpleTest(CouchbaseTestCase):
    def setUp(self):
        super(AdminSimpleTest, self).setUp()
        self.admin = self.make_admin_connection()

    def tearDown(self):
        super(AdminSimpleTest, self).tearDown()
        if self.should_check_refcount:
            rc = sys.getrefcount(self.admin)
            self.assertEqual(rc, 2)

        del self.admin

    def test_http_request(self):
        htres = self.admin.http_request('pools/')
        self.assertIsInstance(htres, HttpResult)
        self.assertIsInstance(htres.value, dict)
        self.assertEqual(htres.http_status, 200)
        self.assertEqual(htres.url, 'pools/')
        self.assertTrue(htres.success)

    def test_connection_string_param(self):

        conn_str = 'http://{0}:{1}'.format(self.cluster_info.host, self.cluster_info.port)
        admin = Admin('Administrator',
                      'password',
                      connection_string=conn_str)
        self.assertIsNotNone(admin)

    def test_bucket_param(self):

        admin = Admin('Administrator',
                      'password',
                      host=self.cluster_info.host,
                      port=self.cluster_info.port,
                      bucket='default')
        self.assertIsNotNone(admin)

    def test_bad_request(self):
        self.assertRaises(HTTPError, self.admin.http_request, '/badpath')

        excraised = 0
        try:
            self.admin.http_request("/badpath")
        except HTTPError as e:
            excraised = 1
            self.assertIsInstance(e.objextra, HttpResult)

        self.assertTrue(excraised)

    def test_bad_args(self):
        self.assertRaises(ArgumentError,
                          self.admin.http_request,
                          None)

        self.assertRaises(ArgumentError,
                          self.admin.http_request,
                          '/',
                          method='blahblah')

    def test_bad_auth(self):
        self.assertRaises(AuthError, Admin,
                          'baduser', 'badpass',
                          host=self.cluster_info.host,
                          port=self.cluster_info.port)

    def test_bad_host(self):
        self.assertRaises(CouchbaseNetworkError, Admin,
                          'user', 'pass', host='127.0.0.1', port=1)

    def test_bad_handle(self):
        self.assertRaises(CouchbaseError, self.admin.upsert, "foo", "bar")
        self.assertRaises(CouchbaseError, self.admin.get, "foo")
        self.assertRaises(CouchbaseError, self.admin.append, "foo", "bar")
        self.assertRaises(CouchbaseError, self.admin.remove, "foo")
        self.assertRaises(CouchbaseError, self.admin.unlock, "foo", 1)
        str(None)

    def test_actions(self):
        if not self.is_realserver:
            raise SkipTest('Real server must be used for admin tests')

        if not os.environ.get('PYCBC_TEST_ADMIN'):
            raise SkipTest('PYCBC_TEST_ADMIN must be set in the environment')

        try:
            # Remove the bucket, if it exists
            self.admin.bucket_remove('dummy')
        except CouchbaseError:
            pass

        # Need to explicitly enable admin tests..
        # Create the bucket
        self.admin.bucket_create(name='dummy',
                                 ram_quota=100, bucket_password='letmein')
        self.admin.wait_ready('dummy', timeout=15.0)

        # All should be OK, ensure we can connect:
        connstr = ConnectionString.parse(
            self.make_connargs()['connection_string'])

        connstr.bucket = 'dummy'
        connstr = connstr.encode()
        self.factory(connstr, password='letmein')
        # OK, it exists
        self.assertRaises(CouchbaseError, self.factory, connstr)

        # Change the password
        self.admin.bucket_update('dummy',
                                 self.admin.bucket_info('dummy'),
                                 bucket_password='')
        self.factory(connstr)  # No password

        # Remove the bucket
        self.admin.bucket_remove('dummy')
        self.assertRaises(CouchbaseError, self.factory, connstr)

    def test_create_ephemeral_bucket_and_use(self):
        bucket_name = 'ephemeral'
        password = 'letmein'

        # create ephemeral test bucket
        self.admin.bucket_create(name=bucket_name,
                                 bucket_type='ephemeral',
                                 ram_quota=100,
                                 bucket_password=password)
        self.admin.wait_ready(bucket_name, timeout=10)

        # connect to bucket to ensure we can use it
        conn_str = "http://{0}:{1}/{2}".format(self.cluster_info.host, self.cluster_info.port, bucket_name)
        bucket = Bucket(connection_string=conn_str, password=password)
        self.assertIsNotNone(bucket)

        # create a doc then read it back
        key = 'mike'
        doc = {'name': 'mike'}
        bucket.upsert(key, doc)
        result = bucket.get(key)

        # original and result should be the same
        self.assertEqual(doc, result.value)

    def test_build_user_management_path(self):

        path = self.admin._get_management_path(AuthDomain.Local)
        self.assertEqual('/settings/rbac/users/local', path)

        path = self.admin._get_management_path(AuthDomain.Local, 'user')
        self.assertEqual('/settings/rbac/users/local/user', path)

        path = self.admin._get_management_path(AuthDomain.Local)
        self.assertEqual('/settings/rbac/users/local', path)

        path = self.admin._get_management_path(AuthDomain.Local, 'user')
        self.assertEqual('/settings/rbac/users/local/user', path)

    def test_create_list_get_remove_internal_user(self):

        userid = 'custom-user'
        password = 's3cr3t'
        roles = [('data_reader', 'default'), ('data_writer', 'default')]

        # add user
        self.admin.user_upsert(AuthDomain.Local, userid, password, roles)

        # get all users
        users = self.admin.users_get(AuthDomain.Local)
        self.assertIsNotNone(users)

        # get single user
        user = self.admin.user_get(AuthDomain.Local, userid)
        self.assertIsNotNone(user)

        # remove user
        self.admin.user_remove(AuthDomain.Local, userid)

    def test_invalid_domain_raises_argument_error(self):

        userid = 'custom-user'
        password = 's3cr3t'
        roles = [('data_reader', 'default'), ('data_writer', 'default')]

        # invalid domain generates argument error
        self.assertRaises(ArgumentError, self.admin.users_get, None)
        self.assertRaises(ArgumentError, self.admin.user_get, None, userid)
        self.assertRaises(ArgumentError, self.admin.user_upsert, None, userid, password, roles)
        self.assertRaises(ArgumentError, self.admin.user_remove, None, userid)
