# dc6006l - CLI/library to control FNIRSI DC Power Supply (DC-6006L, etc)

# What is this?

[FNIRSI DC6006L](http://www.fnirsi.cn/productinfo/556155.html) is a programmable DC power supply
that is quite compact and inexpensive. This CLI tool/library allows you to control an unit
over a built-in USB-serial port.

This work is based on the work by [jcheger](https://github.com/jcheger/fnirsi-dc580-protocol)
for a similar model, DC-580. They seem to support same set of commands, but are not compatible
in message format.

# How to install
```
pip install dc6006l
```

# How to use
```
dc6006l - Controls FNIRSI DC Power Supply (DC-6006L, etc)
Usage: dc6006l [-p devport] [-m model] cmd [cmd...]
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
  $ dc6006l v=1 c=1 on sleep=3 off
  # More complex operation
  $ dc6006l check v=1.5 c=1.0 on flush sep trace=15 c=0.5 flush sep trace=15 off
NOTE:
  - Set envvar FNIRSI_PS=/some/devport to specify default port to use.
```

# NOTE

While this code works for me, your milage may vary.

Just as a head-up, in one case, target voltage was unexpectedly set to 15V
when I sent a command to set to 1.5V (V0150). Because there is no checksum in frame,
I suppose the unit dropped a byte and somehow interpreted as "V1500".
While the hardware is nice, it seems there is a serious issue with firmware
of the product that it easily drops data sent over a serial port.

I added double-check mode (cmd: check) to cope with this, but this mode is
ineffective if you need to change the setting while the unit is already on.
