.. -*- coding: utf-8 -*-
.. Copyright (C) 2025 Benjamin Thomas Schwertfeger
.. GitHub: https://github.com/btschwertfeger
..

.. _need2knows-section:

Need 2 Knows
============

This is a section of the documentation that contains important information
that you need to know. It is important to read this section before you
begin using the software.

What happens to partially filled buy orders?
--------------------------------------------

The algorithm manages its orders in lean way, meaning partially filled buy orders
that may get cancelled will be remembered. This is done internally by saving the
order price and filled amount in order to place a sell order at a higher price
in the future.

The log shows closed connection but the algorithm is still running
------------------------------------------------------------------

In a case where a traceback or warning containing something like "got an
exception no close frame received or sent" is shown in the log, the algorithm
will keep running, as the underlying `python-kraken-sdk`_ library handles the
reconnect.

In case of uncertainty, the kraken-infinity-grid can be started with verbose
logging to see the reconnection process (and more). The verbose logging can be
enabled via ``-v`` for debug logging of the kraken-infinity-grid or ``-vv`` for
even more logging of used packages.
