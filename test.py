
# pylint: disable=redefined-outer-name
import datetime
import getpass
import os
import sqlite3
import sys
import tempfile
import time

import pytest

import slurm2sql
from slurm2sql import unixtime

has_sacct = os.system('sacct --version') == 0


os.environ['TZ'] = 'Europe/Helsinki'
time.tzset()

#
# Fixtures
#
@pytest.fixture()
def db():
    """Test, in-memory database fixture"""
    with sqlite3.connect(':memory:') as db:
        yield db

@pytest.fixture()
def dbfile():
    """Test, in-memory database fixture"""
    with tempfile.NamedTemporaryFile() as dbfile:
        yield dbfile.name

@pytest.fixture()
def slurm_version(monkeypatch, slurm_version_number=(20, 10)):
    print('Setting Slurm version to %s'%(slurm_version_number,))
    monkeypatch.setattr(slurm2sql, 'slurm_version', lambda: slurm_version_number)
    yield

@pytest.fixture()
def slurm_version_2011(monkeypatch, slurm_version_number=(20, 11, 1)):
    print('Setting Slurm version to %s'%(slurm_version_number,))
    monkeypatch.setattr(slurm2sql, 'slurm_version', lambda: slurm_version_number)
    yield


@pytest.fixture(scope='function')
def data1(slurm_version):
    """Test data set 1"""
    lines = open('tests/test-data1.txt')
    yield lines

@pytest.fixture(scope='function')
def data2(slurm_version_2011):
    """Test data set 2.

    This is the same as data1, but removes the ReqGRES column (for slurm>=20.11)
    """
    lines = open('tests/test-data2.txt')
    yield lines


#
# Tests
#
def test_slurm2sql_basic(db, data1):
    slurm2sql.slurm2sql(db, sacct_filter=[], raw_sacct=data1)
    r = db.execute("SELECT JobName, Start "
                   "FROM slurm WHERE JobID=43974388;").fetchone()
    assert r[0] == 'spawner-jupyterhub'
    assert r[1] == 1564601354

def test_main(db, data1):
    slurm2sql.main(['dummy'], raw_sacct=data1, db=db)
    r = db.execute("SELECT JobName, Start "
                   "FROM slurm WHERE JobID=43974388;").fetchone()
    assert r[0] == 'spawner-jupyterhub'
    assert r[1] == 1564601354
    assert db.execute("SELECT count(*) from slurm;").fetchone()[0] == 5

def test_jobs_only(db, data1):
    """--jobs-only gives two rows"""
    slurm2sql.main(['dummy', '--jobs-only'], raw_sacct=data1, db=db)
    assert db.execute("SELECT count(*) from slurm;").fetchone()[0] == 2

def test_verbose(db, data1, caplog):
    slurm2sql.main(['dummy', '--history-days=1', '-v'], raw_sacct=data1, db=db)
    assert time.strftime("%Y-%m-%d") in caplog.text

def test_quiet(db, data1, caplog, capfd):
    slurm2sql.main(['dummy', '-q'], raw_sacct=data1, db=db)
    slurm2sql.main(['dummy', '--history=1-5', '-q'], raw_sacct=data1, db=db)
    slurm2sql.main(['dummy', '--history-days=1', '-q'], raw_sacct=data1, db=db)
    slurm2sql.main(['dummy', '--history-start=2019-01-01', '-q'], raw_sacct=data1, db=db)
    #assert caplog.text == ""
    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""

def test_time(db, data1):
    slurm2sql.main(['dummy'], raw_sacct=data1, db=db)
    r = db.execute("SELECT Time FROM slurm WHERE JobID=43974388;").fetchone()[0]
    assert r == unixtime('2019-08-01T02:02:39')
    # Submit defined, Start defined, End='Unknown' --> timestamp should be "now"
    r = db.execute("SELECT Time FROM slurm WHERE JobID=43977780;").fetchone()[0]
    assert r >= time.time() - 5
    # Job step: Submit defined, Start='Unknown', End='Unknown' --> Time should equal Submit
    r = db.execute("SELECT Time FROM slurm WHERE JobIDSlurm='43977780.batch';").fetchone()[0]
    assert r == unixtime('2019-08-01T00:35:27')


#
# Test command line
#
@pytest.mark.skipif(not has_sacct, reason="Can only be tested with sacct")
def test_cmdline(dbfile):
    ten_days_ago = (datetime.datetime.today() - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    five_days_ago = (datetime.datetime.today() - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    os.system('python3 slurm2sql.py %s -- -S %s'%(dbfile, ten_days_ago))
    os.system('python3 slurm2sql.py %s -- -S %s -E %s'%(
        dbfile, ten_days_ago, five_days_ago))
    sqlite3.connect(dbfile).execute('SELECT JobName from slurm;')

@pytest.mark.skipif(not has_sacct, reason="Can only be tested with sacct")
def test_cmdline_history_days(dbfile):
    os.system('python3 slurm2sql.py --history-days=10 %s --'%dbfile)
    sqlite3.connect(dbfile).execute('SELECT JobName from slurm;')

@pytest.mark.skipif(not has_sacct, reason="Can only be tested with sacct")
def test_cmdline_history_start(dbfile):
    ten_days_ago = (datetime.datetime.today() - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    os.system('python3 slurm2sql.py --history-start=%s %s --'%(ten_days_ago, dbfile))
    sqlite3.connect(dbfile).execute('SELECT JobName from slurm;')

@pytest.mark.skipif(not has_sacct, reason="Can only be tested with sacct")
def test_cmdline_history(dbfile):
    print('x')
    os.system('python3 slurm2sql.py --history=2-10 %s --'%dbfile)
    sqlite3.connect(dbfile).execute('SELECT JobName from slurm;')


#
# Misc function tests
#
def test_binary_units():
    assert slurm2sql.int_bytes('2k') == 2048
    assert slurm2sql.int_bytes('2M') == 2 * 2**20
    assert slurm2sql.int_bytes('2G') == 2 * 2**30
    assert slurm2sql.int_bytes('2T') == 2 * 2**40
    assert slurm2sql.int_bytes('2p') == 2 * 2**50
    assert isinstance(slurm2sql.int_bytes('2k'), int)

    assert slurm2sql.float_bytes('2k') == 2048
    assert slurm2sql.float_bytes('2M') == 2 * 2**20
    assert slurm2sql.float_bytes('2G') == 2 * 2**30
    assert slurm2sql.float_bytes('2t') == 2 * 2**40
    assert slurm2sql.float_bytes('2P') == 2 * 2**50
    assert isinstance(slurm2sql.float_bytes('2k'), float)

def test_metric_units():
    assert slurm2sql.int_metric('2k') == 2 * 1000**1
    assert slurm2sql.int_metric('2M') == 2 * 1000**2
    assert slurm2sql.int_metric('2G') == 2 * 1000**3
    assert slurm2sql.int_metric('2T') == 2 * 1000**4
    assert slurm2sql.int_metric('2p') == 2 * 1000**5
    assert isinstance(slurm2sql.int_metric('2k'), int)

    assert slurm2sql.float_metric('2k') == 2 * 1000**1
    assert slurm2sql.float_metric('2M') == 2 * 1000**2
    assert slurm2sql.float_metric('2G') == 2 * 1000**3
    assert slurm2sql.float_metric('2t') == 2 * 1000**4
    assert slurm2sql.float_metric('2P') == 2 * 1000**5
    assert isinstance(slurm2sql.float_metric('2k'), float)

def test_slurm_time():
    assert slurm2sql.slurmtime('1:00:00') == 3600
    assert slurm2sql.slurmtime('1:10:00') == 3600 + 600
    assert slurm2sql.slurmtime('1:00:10') == 3600 + 10
    assert slurm2sql.slurmtime('00:10') == 10
    assert slurm2sql.slurmtime('10:10') == 600 + 10
    assert slurm2sql.slurmtime('10') == 60 * 10  # default is min
    assert slurm2sql.slurmtime('3-10:00') == 3600*24*3 + 10*3600
    assert slurm2sql.slurmtime('3-13:10:00') == 3600*24*3 + 13*3600 + 600
    assert slurm2sql.slurmtime('3-13:10') == 3600*24*3 + 13*3600 + 600
    assert slurm2sql.slurmtime('3-13') == 3600*24*3 + 13*3600

def test_history_last_timestamp(db, slurm_version):
    """Test update_last_timestamp and get_last_timestamp functions"""
    import io
    # initialize db with null input - this just forces table creation.
    slurm2sql.slurm2sql(db, raw_sacct=io.StringIO())
    # Set last update and get it again immediately
    slurm2sql.update_last_timestamp(db, 13)
    assert slurm2sql.get_last_timestamp(db) == 13

def test_history_resume_basic(db, data1):
    """Test --history-resume"""
    # Run it once.  Is the update_time approximately now?
    slurm2sql.main(['dummy', '--history-days=1'], raw_sacct=data1, db=db)
    update_time = slurm2sql.get_last_timestamp(db)
    assert abs(update_time - time.time()) < 5
    # Wait 1s, is update time different?
    time.sleep(1.1)
    slurm2sql.main(['dummy', '--history-resume'], raw_sacct=data1, db=db)
    assert update_time != slurm2sql.get_last_timestamp(db)

def test_history_resume_timestamp(db, data1, caplog):
    """Test --history-resume's exact timestamp"""
    # Run once to get an update_time
    slurm2sql.main(['dummy', '--history-days=1'], raw_sacct=data1, db=db)
    update_time = slurm2sql.get_last_timestamp(db)
    caplog.clear()
    # Run again and make sure that we filter based on that update_time
    slurm2sql.main(['dummy', '--history-resume'], raw_sacct=data1, db=db)
    assert slurm2sql.slurm_timestamp(update_time) in caplog.text

@pytest.mark.parametrize(
    "string,version",
    [("slurm 20.11.1", (20, 11, 1)),
     ("slurm 19.5.0", (19, 5, 0)),
     ("slurm 19.05.7-Bull.1.0", (19, 5, 7)),
    ])
def test_slurm_version(string, version):
    """Test slurm version detection"""
    v = slurm2sql.slurm_version(cmd=['echo', string])
    assert v == version


# Test slurm 20.11 version
#@pytest.mark.parametrize('slurm_version_number', [(20, 12, 5)])
def test_slurm2011_gres(db, data2):
    """Test 20.11 compatibility, using ReqTRES instead of ReqGRES.

    This asserts that the ReqGRES column is *not* in the database with Slurm > 20.11
    """
    test_slurm2sql_basic(db, data2)
    with pytest.raises(sqlite3.OperationalError, match='no such column:'):
        db.execute('SELECT ReqGRES FROM slurm;')



#
# Test data generation
#
def make_test_data():
    """Create current testdata from the slurm DB"""
    slurm_cols = tuple(c for c in slurm2sql.COLUMNS.keys() if not c.startswith('_'))
    lines = slurm2sql.sacct(slurm_cols, ['-S', '2019-08-01', '-E', '2019-08-31'])
    f = open('tests/test-data1.txt', 'w')
    for line in lines:
        line = line.replace(getpass.getuser(), 'user1')
        f.write(line)
    f.close()



if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'maketestdata':
        make_test_data()
