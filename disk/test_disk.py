# (C) Datadog, Inc. 2010-2017
# All rights reserved
# Licensed under Simplified BSD License (see LICENSE)

# stdlib
import os
import re

# 3p
import mock
from nose.plugins.attrib import attr

# project
from tests.checks.common import AgentCheckTest, Fixtures

DEFAULT_DEVICE_NAME = '/dev/sda1'
FIXTURE_DIR = os.path.join(os.path.dirname(__file__), 'ci')

class MockPart(object):
    def __init__(self, device=DEFAULT_DEVICE_NAME, fstype='ext4',
                 mountpoint='/'):
        self.device = device
        self.fstype = fstype
        self.mountpoint = mountpoint


class MockDiskMetrics(object):
    def __init__(self):
        self.total = 5 * 1024
        self.used = 4 * 1024
        self.free = 1 * 1024
        self.percent = 80


class MockInodesMetrics(object):
    def __init__(self):
        self.f_files = 10
        self.f_ffree = 9


class MockIoCountersMetrics(object):
    def __init__(self):
        self.read_time = 15
        self.write_time = 25

@attr('unix')
class TestCheckDisk(AgentCheckTest):
    CHECK_NAME = 'disk'

    GAUGES_VALUES = {
        'system.disk.total': 5,
        'system.disk.used': 4,
        'system.disk.free': 1,
        'system.disk.in_use': .80,
        'system.fs.inodes.total': 10,
        'system.fs.inodes.used': 1,
        'system.fs.inodes.free': 9,
        'system.fs.inodes.in_use': .10
    }

    GAUGES_VALUES_PSUTIL = {
        'system.disk.read_time_pct': 1.5,
        'system.disk.write_time_pct': 2.5,
    }

    DISK_GAUGES = [
        'system.disk.free',
        'system.disk.in_use',
        'system.disk.total',
        'system.disk.used'
    ]

    INODE_GAUGES = [
        'system.fs.inodes.total',
        'system.fs.inodes.used',
        'system.fs.inodes.free',
        'system.fs.inodes.in_use'
    ]

    # Really a basic check to see if all metrics are there
    def test_disk_check(self):
        self.run_check({'instances': [{'use_mount': 'no'}]})

        # Assert metrics
        for metric in self.DISK_GAUGES + self.INODE_GAUGES:
            self.assertMetric(metric, tags=[])

        self.coverage_report()

    # Test two instances
    def test_bad_config(self):
        self.assertRaises(Exception,
                          lambda: self.run_check({'instances': [{}, {}]}))

    def test_device_exclusion_logic(self):
        self.run_check({'instances': [{'use_mount': 'no',
                                       'excluded_filesystems': ['aaaaaa'],
                                       'excluded_mountpoint_re': '^/run$',
                                       'excluded_disks': ['bbbbbb'],
                                       'excluded_disk_re': '^tev+$'}]},
                       mocks={'collect_metrics': lambda: None})
        # should pass, default mock is a normal disk
        exclude_disk = self.check._exclude_disk_psutil
        self.assertFalse(exclude_disk(MockPart()))

        # standard fake devices
        self.assertTrue(exclude_disk(MockPart(device='')))
        self.assertTrue(exclude_disk(MockPart(device='none')))
        self.assertFalse(exclude_disk(MockPart(device='udev')))

        # excluded filesystems list
        self.assertTrue(exclude_disk(MockPart(fstype='aaaaaa')))
        self.assertFalse(exclude_disk(MockPart(fstype='a')))

        # excluded devices list
        self.assertTrue(exclude_disk(MockPart(device='bbbbbb')))
        self.assertFalse(exclude_disk(MockPart(device='b')))

        # excluded devices regex
        self.assertTrue(exclude_disk(MockPart(device='tevvv')))
        self.assertFalse(exclude_disk(MockPart(device='tevvs')))

        # and now with all_partitions
        self.check._all_partitions = True
        self.assertFalse(exclude_disk(MockPart(device='')))
        self.assertFalse(exclude_disk(MockPart(device='none')))
        self.assertFalse(exclude_disk(MockPart(device='udev')))

        # excluded mountpoint regex
        self.assertTrue(exclude_disk(MockPart(device='sdz', mountpoint='/run')))
        self.assertFalse(exclude_disk(MockPart(device='sdz', mountpoint='/run/shm')))

    def test_device_exclusion_logic_no_name(self):
        """
        Same as above but with default configuration values and device='' to expose a bug in #2359
        """
        self.run_check({'instances': [{'use_mount': 'yes',
                                       'excluded_mountpoint_re': '^/run$',
                                       'all_partitions': 'yes'}]},
                       mocks={'collect_metrics': lambda: None}, force_reload=True)
        exclude_disk = self.check._exclude_disk_psutil
        self.assertTrue(exclude_disk(MockPart(device='', mountpoint='/run')))
        self.assertFalse(exclude_disk(MockPart(device='', mountpoint='/run/shm')))

    @mock.patch('psutil.disk_partitions', return_value=[MockPart()])
    @mock.patch('psutil.disk_usage', return_value=MockDiskMetrics())
    @mock.patch('os.statvfs', return_value=MockInodesMetrics())
    def test_psutil(self, mock_partitions, mock_usage, mock_inodes):
        # Mocking
        mock_usage.__name__ = "foo"
        mock_inodes.__name__ = "foo"
        mock_partitions.__name__ = "foo"

        # Run check
        for tag_by in ['yes', 'no']:
            self.run_check({'instances': [{'tag_by_filesystem': tag_by}]},
                           force_reload=True)

            # Assert metrics
            tags = ['ext4', 'filesystem:ext4'] if tag_by == 'yes' else []
            for metric, value in self.GAUGES_VALUES.iteritems():
                self.assertMetric(metric, value=value, tags=tags,
                                  device_name=DEFAULT_DEVICE_NAME)

            self.coverage_report()

    @mock.patch('psutil.disk_partitions', return_value=[MockPart()])
    @mock.patch('psutil.disk_usage', return_value=MockDiskMetrics())
    @mock.patch('os.statvfs', return_value=MockInodesMetrics())
    def test_use_mount(self, mock_partitions, mock_usage, mock_inodes):
        # Mocking
        mock_usage.__name__ = "foo"
        mock_inodes.__name__ = "foo"
        mock_partitions.__name__ = "foo"

        # Run check
        self.run_check({'instances': [{'use_mount': 'yes'}]})

        # Assert metrics
        for metric, value in self.GAUGES_VALUES.iteritems():
            self.assertMetric(metric, value=value, tags=[],
                              device_name='/')

        self.coverage_report()

    @mock.patch('_disk.get_subprocess_output',
                return_value=(Fixtures.read_file('debian-df-Tk', sdk_dir=FIXTURE_DIR), "", 0))
    @mock.patch('os.statvfs', return_value=MockInodesMetrics())
    def test_no_psutil_debian(self, mock_df_output, mock_statvfs):
        mock_statvfs.__name__ = "foo"
        mock_df_output.__name__ = "foo"
        self.run_check({'instances': [{'use_mount': 'no',
                                       'excluded_filesystems': ['tmpfs']}]},
                       mocks={'_psutil': lambda: False})

        for metric, value in self.GAUGES_VALUES.iteritems():
            self.assertMetric(metric, value=value, tags=[],
                              device_name=DEFAULT_DEVICE_NAME)
            # backward compatibility with the old check
            self.assertMetric(metric, tags=[], device_name='udev')

        self.coverage_report()

    @mock.patch('_disk.get_subprocess_output',
                return_value=(Fixtures.read_file('freebsd-df-Tk', sdk_dir=FIXTURE_DIR), "", 0))
    @mock.patch('os.statvfs', return_value=MockInodesMetrics())
    def test_no_psutil_freebsd(self, mock_df_output, mock_statvfs):
        mock_statvfs.__name__ = "foo"
        mock_df_output.__name__ = "foo"

        self.run_check({'instances': [{'use_mount': 'no',
                                       'excluded_filesystems': ['devfs'],
                                       'excluded_disk_re': 'zroot/.+'}]},
                       mocks={'_psutil': lambda: False})

        for metric, value in self.GAUGES_VALUES.iteritems():
            self.assertMetric(metric, value=value, tags=[],
                              device_name='zroot')

        self.coverage_report()

    @mock.patch('_disk.get_subprocess_output',
                return_value=(Fixtures.read_file('centos-df-Tk', sdk_dir=FIXTURE_DIR), "", 0))
    @mock.patch('os.statvfs', return_value=MockInodesMetrics())
    def test_no_psutil_centos(self, mock_df_output, mock_statvfs):
        mock_statvfs.__name__ = "foo"
        mock_df_output.__name__ = "foo"

        self.run_check({'instances': [{'use_mount': 'no',
                                       'excluded_filesystems': ['devfs', 'tmpfs'],
                                       'excluded_disks': ['/dev/sda1']}]},
                       mocks={'_psutil': lambda: False})
        for device in ['/dev/sda3', '10.1.5.223:/vil/cor']:
            for metric, _ in self.GAUGES_VALUES.iteritems():
                self.assertMetric(metric, device_name=device)

        self.coverage_report()

    def test_legacy_option(self):
        # First, let's check that it actually retrieves from the agent config
        self.load_check({'instances': [{}]}, agent_config={'use_mount': 'yes'})
        self.assertTrue(self.check._use_mount)

        # Then let's check that check option overrides datadog.conf
        self.load_check({'instances': [{'use_mount': 'no'}]},
                        agent_config={'use_mount': 'yes'})
        self.assertFalse(self.check._use_mount)

    # FIXME: test default options on Windows (not the same all_partitions)
    def test_default_options(self):
        self.load_check({'instances': [{}]})
        self.check._load_conf({})

        self.assertFalse(self.check._use_mount)
        self.assertEqual(self.check._excluded_filesystems, ['iso9660'])
        self.assertEqual(self.check._excluded_disks, [])
        self.assertFalse(self.check._tag_by_filesystem)
        self.assertFalse(self.check._all_partitions)
        self.assertEqual(self.check._excluded_disk_re, re.compile('^$'))

    def test_ignore_empty_regex(self):
        """
        Ignore empty regex as they match all strings
        (and so exclude all disks from the check)
        """
        self.load_check({'instances': [{}]}, agent_config={'device_blacklist_re': ''})
        self.check._load_conf({})
        self.assertEqual(self.check._excluded_disk_re, re.compile('^$'))
