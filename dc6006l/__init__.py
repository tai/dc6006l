#!/usr/bin/env python3
"""
Unofficial CLI tool to control FNIRSI Power Source (DC6006L, etc)

This code is based on info/code for DC-580 available at

- https://github.com/jcheger/fnirsi-dc580-protocol

DC6006L supports similar protocol, but it differs in various details, hence this code.

While this code works for me, your milage may vary.

In one case, target voltage was unexpectedly set to 15V when I sent a
command to set to 1.5V (V0150). Because there is no checksum in frame,
I suppose the unit dropped a byte which caused it to interpret as "V1500".

I added double-check mode to cope with this, but this mode is
ineffective if you need to change the setting while the unit is already on.
"""

import sys
import os
import time
import re
import json
import logging

from serial import Serial
from argparse import ArgumentParser

log = logging.getLogger(__name__)

def usage_format():
  p = os.path.basename(sys.argv[0])
  return """
{p} - Controls FNIRSI DC Power Supply (DC-6006L, etc)
Usage: {p} [-p devport] [-m model] cmd [cmd...]
Commands:
  on: Turn power on
  off: Turn power off
  v=<V>: Set target voltage
  c=<A>: Set target current
  ovp=<V>: Set over-voltage limit
  ocp=<A>: Set over-current limit
  opp=<W>: Set over-power limit
  ohp=<sec>: Set over-hour limit (0 to disable)
  noprotect: Disable protection
  stat: Show status (packed trace)
  trace=<n>: Show trace capture (infinite if n=-1)
  flush: Flush/clear log buffer
  echo=<str>: Print given input
  sep: Print separator string
  sleep=<sec>: Sleep for given seconds
  check: Enable double-check mode
Example:
  # Output 1V1A for ~3s
  $ {p} v=1 c=1 on sleep=3 off
  # More complex operation
  $ {p} check v=1.5 c=1.0 on flush sep trace=15 c=0.5 flush sep trace=15 off
NOTE:
  - Set envvar FNIRSI_PS=/some/devport to specify default port to use.
""".lstrip().format(**locals())

def usage():
  sys.stderr.write(usage_format())
  sys.exit(0)

class GenericPS(object):
  def __init__(self, port, delay=0.5):
    self.sio = Serial(port, baudrate=115200, xonxoff=True)
    self.delay = delay
    self.check_mode = False
    self.flush()

  def flush(self):
    """Stops logging and clears internal buffer"""
    self.set('log', 0)
    for i in range(3):
      if self.sio.read(self.sio.in_waiting) == b'':
        return True
      time.sleep(self.delay)
    return False

  def send(self, cmd):
    """Sends low-level control command"""
    log.debug("send: " + cmd)
    time.sleep(self.delay)
    self.sio.write((cmd + "\r\n").encode('ascii'))

  def set(self, key, value):
    """Controls an unit with high-level parameter. Note units are in V/A/W"""

    log.debug("set: k=%s, v=%s" % (key, value))

    if key == 'check':
      self.check_mode = True if value else False

    elif key in ('power', 'enable'):
      self.send("N" if value else "F")

    elif key in ('log', 'logging'):
      self.send("Q" if value else "W")

    elif key == 'noprotect' and value:
      self.send("Z")

    elif key in ('v', 'voltage'):
      self.send("V%04d" % (value * 100))
      if self.check_mode: self.check('target_voltage', value)

    elif key in ('c', 'current'):
      self.send("I%04d" % (value * 1000))
      if self.check_mode: self.check('target_current', value)

    elif key == 'ovp':
      self.send("B%04d" % (value * 100))

    elif key == 'ocp':
      self.send("D%04d" % (value * 1000))

    elif key == 'opp':
      self.send("E%04d" % (value * 10))

    elif key == 'ohp':
      self.send("H%02d" % (value / 3600))
      self.send("M%02d" % ((value % 3600) / 60))
      self.send("S%02d" % (value % 60))

    elif key == 'ohp_enable':
      self.send("X" if value else "Y")

    elif key in ('mem', 'memory'):
      self.send("O" if value == 'm1' else "P")

  def check(self, key, value):
    """Read back and check if parameter is set as specified"""
    self.set('log', 0)
    self.set('log', 1)
    stat = self.stat(10)

    ret = stat.get(key)
    if stat.get(key) != value:
      raise ValueError("Unexpected value: {}={} (expected: {})".format(key, ret, value))
      sys.exit(1)

    log.debug("OK: {}={} (expected: {})".format(key, ret, value))

  def on(self):
    """Powers on an unit"""
    self.set('power', 1)

  def off(self):
    """Powers off an unit"""
    self.set('power', 0)

  def stat(self, nr=3):
    """Returns a merged dict of several log trace captures"""
    stat = {}
    for ret in self.trace(nr=nr):
      if ret:
        stat.update(ret)
    return stat if stat else None

  def trace(self, nr=10, timeout=None):
    """Returns a stream of log trace captures"""

    if timeout is None:
      timeout = nr * 1.5

    t0 = time.time()
    buf = b''
    while (nr != 0) and (timeout > 0 and (time.time() - t0) < timeout):
      buf += self.sio.read(self.sio.in_waiting)
      log.debug("buf: " + buf.decode('ascii'))

      stat, rest = self.parse_status(buf)
      if stat:
        yield stat
        buf = rest
        if nr > 0:
          nr -= 1
      else:
        time.sleep(self.delay)

  def dump(self):
    """Dumps serial port data"""
    while True:
      buf = self.sio.read(self.sio.in_waiting)
      print(buf.decode('ascii'))
      time.sleep(self.delay)

  def parse_status(self, buf):
    """Extracts first valid log from given buffer. Also returns remaining buffer."""

    #
    # Check match with various possible fragment patterns
    #
    # This is needed as DC6006L emits mixed output of these fragments, instead of
    # emitting single fixed formatted output. So the output is like following:
    #
    #   KB<type0><type1><type3><type0>...<type0><type1><type0><type3><type0>...<type0>
    #
    # First 'KB' prefix is emitted only on first connection setup.
    #
    # On DC580, this prefix seems to be 'MB' and format of each fragment also
    # somewhat differs.
    #
    results = [
      # type-0 fragment
      re.match(''.join([
        '(?P<voltage>\d{4})A', '(?P<current>\d{4})A', '(?P<power>\d{4})A',
        '(\d)A',
        '(?P<temperature>\d{3})A',
        '(?P<mode>\d)A', '(?P<cause>\d)A', '(?P<enable>\d)A',
      ]), buf.decode('ascii')),

      # type-1 fragment
      re.match(''.join([
        '(?P<ovp>\d{4})A', '(?P<ocp>\d{4})A', '(?P<opp>\d{4,5})A',
        '(?P<ohp_enable>\d)A', '(?P<ohp_h>\d\d)A', '(?P<ohp_m>\d\d)A', '(?P<ohp_s>\d\d)A',
      ]), buf.decode('ascii')),

      # type-2 fragment
      re.match(''.join([
        '(?P<target_voltage>\d{4})A', '(?P<target_current>\d{4})A',
      ]), buf.decode('ascii')),

      # type-3 fragment (type-0 with leading garbage)
      re.match(''.join([
        '.*?',
        '(?P<voltage>\d{4})A', '(?P<current>\d{4})A', '(?P<power>\d{4})A',
        '(\d)A',
        '(?P<temperature>\d{3})A',
        '(?P<mode>\d)A', '(?P<cause>\d)A', '(?P<enable>\d)A',
      ]), buf.decode('ascii')),
    ]

    # take the first valid match
    for frag_type,ret in enumerate(results):
      if ret is None: continue

      stat = {}
      for k,v in ret.groupdict().items():
        if v is not None: stat[k] = int(v)

      log.debug(json.dumps(stat))

      if frag_type in (0, 3):
        stat['voltage'] /= 100
        stat['current'] /= 1000
        stat['power'] /= 100
        stat['mode'] = 'CV' if stat['mode'] == 0 else 'CC'
        stat['cause'] = ['none', 'OVP', 'OCP', 'OPP', 'OTP', 'OHP'][stat['cause']]

      elif frag_type == 1:
        stat['ovp'] /= 100
        stat['opp'] /= 100

      elif frag_type == 2:
        stat['target_voltage'] /= 100
        stat['target_current'] /= 1000

      return stat, buf[ret.end():]

    return None, buf

class DC6006L(GenericPS):
  pass

class DC580(GenericPS):
  pass

def handle_command(opt):
  dc = eval(opt.model)(opt.port)

  for cmd in opt.args:
    ret = re.match('(\w+)(?:=(\S+))?', cmd)
    if not ret:
      continue

    cmd, val = ret.groups()
    if cmd in ('noprotect', 'check', 'sleep') and val is None:
      val = 1

    if cmd == 'echo':
      print(val)

    elif cmd == 'sep':
      print("#" + "-" * 60)

    elif cmd == 'sleep':
      time.sleep(float(val))

    elif cmd == 'on':
      dc.on()

    elif cmd == 'off':
      dc.off()

    elif cmd == 'cmd':
      dc.send(val)

    elif cmd == 'dump':
      dc.dump()

    elif cmd == 'flush':
      dc.flush()

    elif cmd == 'mem':
      dc.set(cmd, val)

    elif cmd == 'stat':
      dc.flush()
      dc.set('log', 1)
      stat = dc.stat()
      print(json.dumps(stat))

    elif cmd == 'trace':
      dc.set('log', 1)
      for stat in dc.trace(int(val)):
        print(json.dumps(stat))

    elif cmd == 'ohp':
      if int(val) > 0:
        dc.set(cmd, int(val))
        dc.set('ohp_enable', 1)
      else:
        dc.set('ohp_enable', 0)

    else:
      dc.set(cmd, float(val))

def main():
  default_port = os.getenv("FNIRSI_PS") or '/dev/fnirsi-ps0'

  ap = ArgumentParser()
  ap.print_help = usage
  ap.add_argument('-D', '--debug', nargs='?', default='INFO')
  ap.add_argument('-m', '--model', type=str, default='GenericPS')
  ap.add_argument('-p', '--port', type=str, default=default_port)
  ap.add_argument('args', nargs='*')

  opt = ap.parse_args()

  logging.basicConfig(level=eval('logging.' + opt.debug))

  if len(opt.args) == 0:
    usage()

  handle_command(opt)

if __name__ == '__main__':
  main()
