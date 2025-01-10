.. -*- coding: utf-8 -*-
.. Copyright (C) 2025 Benjamin Thomas Schwertfeger
.. GitHub: https://github.com/btschwertfeger
..

Strategies
==========

Information about terms used
----------------------------

- **Base currency**: The base currency is the currency that is being bought and
  sold, e.g. BTC. for the symbol BTC/EUR.

- **Quote currency**: The quote currency is the currency that is being used to
  buy and sell the base currency, e.g. EUR. for the symbol BTC/EUR.

- **Price**: The price is the current price of the base currency in terms of the
  quote currency, e.g. 100,000 USD for 1 BTC, 100,000 is the price.

- **Grid interval**: The grid interval is the percentage difference between the
  placed buy orders, e.g. 4 %. If the current price rises 'to high', the placed
  buy orders will be cancelled and new buy orders will be placed 'interval' %
  below the current price (shifting up). The interval for buy orders is always
  based on the current price _or_ the next higher buy order, e.g. if the current
  price is 100,000 USD and the interval is 4 %, the first buy order will be
  placed at 96,000 USD, the second buy order at 92,160 USD, the third buy order
  at 88,4736 USD, and so on. The interval for sell orders is usually based on
  the buy price, e.g. if the buy price was 100,000 USD, the sell order will be
  placed for 104,000 USD.

- **Shifting up**: Shifting up is the process of canceling and replacing the buy
  orders if the current price rises above a certain threshold, which is
  :math:`(p\cdot(1+i))^2*1.001` where :math:`p` is the highest price of an
  existing, unfilled buy order and :math:`i` is the interval (e.g. 4 %, i.e.
  0.04). This technique ensures that buy orders don't get out of scope.

Available strategies
--------------------

.. _strategies-gridhodl-section:

GridHODL
~~~~~~~~

The *GridHODL* strategy is a grid trading strategy that buys and sells at fixed
intervals, e.g. every 4 %. The algorithm places :math:`n` buy orders below the
current price and waits for their execution to then execute the arbitrage and
place a sell order for the bought base currency at 4 % higher. The key idea here
is to accumulate a bit of the base currency over time, as the order size in
terms of quote volume is fixed, e.g. to 100 USD.

.. _strategies-gridsell-section:

GridSell
~~~~~~~~

The *GridSell* strategy is the counterpart of the GridHODL strategy, as it
creates a sell order for 100 % of the base currency bought by a single buy
order, e.g. if a buy order for 100 USD worth of BTC is executed and the interval
is set to 4 %, the sell order size will be 104 USD worth of BTC.

.. _strategies-swing-section:

SWING
~~~~~

The *SWING* strategy is another variation of the GridHODL strategy, as it does
the same but with a twist. The idea is to sell the base currency if the price
rises above the highest price for which the algorithm has bought the currency,
e.g. if the algorithm traded and accumulated a lot of BTC/USD between
40,000-80,000 USD and the highest price for which the algorithm has bought BTC
was 80,000 USD, the algorithm will start placing sell orders at a fixed interval
(e.g. 4 %) if the price rises above 80,000 USD, e.g. to sell 100 USD worth of
BTC at 83,200 USD while further accumulating the currency trades below the
highest buy price.

.. NOTE:: ⚠️ It also starts selling the already existing base currency above the
          current price. This should be kept in mind when choosing this
          strategy.

.. _strategies-cdca-section:

cDCA
~~~~

The *cDCA* strategy is a dollar-cost averaging strategy that buys at fixed
intervals for a fixed size, e.g. 100 USD worth of BTC every 4 % without placing
sell orders in order to accumulate the base currency over team for speculating
on rising value in the long run. The difference to classical DCA strategies is
that even if the price rises, the algorithm will shift-up buy orders instead of
getting out of scope.
