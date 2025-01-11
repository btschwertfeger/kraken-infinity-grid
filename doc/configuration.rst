.. -*- coding: utf-8 -*-
.. Copyright (C) 2025 Benjamin Thomas Schwertfeger
.. GitHub: https://github.com/btschwertfeger
..

.. _configuration-section:

Configuration
=============

The algorithm is designed to be highly configurable and can be adjusted to your
needs. The following configuration variables can be either set as command-line
arguments or via environment variables. They are mapped to the corresponding
command-line arguments internally.

Command-line Interface
-----------------------

`kraken-infinity-grid`_ provides a command-line interface (CLI) to configure and
run the trading algorithm. The CLI is based on the `Click
<https://click.palletsprojects.com>`_ library and provides a set of commands to
interact with the algorithm.


.. click:: kraken_infinity_grid.cli:cli
   :prog: kraken-infinity-grid
   :nested: full

Environment Variables
---------------------

Since `kraken-infinity-grid`_ is designed to be run in containerized
environments, the configuration can also be done via environment variables. The
naming pattern follows the convention of the command-line arguments respecting
the ``KRAKEN_`` prefix and `Click's
<https://click.palletsprojects.com/en/stable/options/#values-from-environment-variables>`_
naming convention.

.. list-table:: Configuration Variables
    :header-rows: 1

    * - Variable
      - Type
      - Description
    * - ``KRAKEN_API_KEY``
      - ``str``
      - Your Kraken API key.
    * - ``KRAKEN_SECRET_KEY``
      - ``str``
      - Your Kraken secret key.
    * - ``KRAKEN_RUN_NAME``
      - ``str``
      - The name of the instance. Can be any name that is used to differentiate
        between instances of the kraken-infinity-grid.
    * - ``KRAKEN_RUN_USERREF``
      - ``int``
      - A reference number to identify the algorithm's orders. This can be a
        timestamp or any integer number.
        **Use different userref's for different algorithms!**
    * - ``KRAKEN_BOT_VERBOSE``
      - ``int`` / (``-v``, ``-vv``)
      - Enable verbose logging.
    * - ``KRAKEN_DRY_RUN``
      - ``bool``
      - Enable dry-run mode (no actual trades).
    * - ``KRAKEN_RUN_BASE_CURRENCY``
      - ``str``
      - The base currency e.g., ``BTC`` or ``ETH``.
    * - ``KRAKEN_RUN_QUOTE_CURRENCY``
      - ``str``
      - The quote currency e.g., ``USD`` or ``EUR``.
    * - ``KRAKEN_RUN_AMOUNT_PER_GRID``
      - ``float``
      - The quote amount to use per grid interval e.g., ``100`` (USD) per trade.
    * - ``KRAKEN_RUN_INTERVAL``
      - ``float``
      - The interval between orders e.g., ``0.04`` to have 4 % intervals.
    * - ``KRAKEN_RUN_N_OPEN_BUY_ORDERS``
      - ``int``
      - The number of concurrent open buy orders e.g., ``5``. The number of
        always open buy positions specifies how many buy positions should be
        open at the same time. If the interval is defined to 2%, a number of 5
        open buy positions ensures that a rapid price drop of almost 10% that
        can be caught immediately.
    * - ``KRAKEN_RUN_MAX_INVESTMENT``
      - ``str``
      - The maximum investment, e.g. ``1000`` USD.
    * - ``KRAKEN_RUN_FEE``
      - ``float``
      - A custom fee percentage, e.g. ``0.0026`` for 0.26 % fee.
    * - ``KRAKEN_RUN_STRATEGY``
      - ``str``
      - The trading strategy (e.g., ``GridHODL``, ``GridSell``, ``SWING``, or ``cDCA``).
    * - ``KRAKEN_RUN_TELEGRAM_TOKEN``
      - ``str``
      - The Telegram bot token for notifications.
    * - ``KRAKEN_RUN_TELEGRAM_CHAT_ID``
      - ``str``
      - The Telegram chat ID for notifications.
    * - ``KRAKEN_RUN_EXCEPTION_TOKEN``
      - ``str``
      - The Telegram bot token for exception notifications.
    * - ``KRAKEN_RUN_EXCEPTION_CHAT_ID``
      - ``str``
      - The Telegram chat ID for exception notifications.
    * - ``KRAKEN_RUN_DB_USER``
      - ``str``
      - The PostgreSQL database user.
    * - ``KRAKEN_RUN_DB_NAME``
      - ``str``
      - The PostgreSQL database name.
    * - ``KRAKEN_RUN_DB_PASSWORD``
      - ``str``
      - The PostgreSQL database password.
    * - ``KRAKEN_RUN_DB_HOST``
      - ``str``
      - The PostgreSQL database host.
    * - ``KRAKEN_RUN_DB_PORT``
      - ``int``
      - The PostgreSQL database port.
    * - ``KRAKEN_RUN_SQLITE_FILE``
      - ``str``
      - The path to a local SQLite database file, e.g., ``/path/to/sqlite.db``,
        will be created if it does not exist.

.. _database-configuration-section:

Database Configuration
----------------------

The algorithm requires a PostgreSQL or SQLite database to store the current
orderbook, trades, and the algorithm's state. The database configuration can be
set via environment variables or command-line arguments.

PostgreSQL
~~~~~~~~~~

When using the algorithm as proposed in :ref:`Getting Started
<getting-started-docker-compose-section>` via the provided Docker Compose file,
the PostgreSQL database is automatically configured.

The algorithm requires the following environment variables to be set, in order
to connect to the PostgreSQL database:

- ``KRAKEN_RUN_DB_USER``
- ``KRAKEN_RUN_DB_NAME``
- ``KRAKEN_RUN_DB_PASSWORD``
- ``KRAKEN_RUN_DB_HOST``
- ``KRAKEN_RUN_DB_PORT``

SQLite
~~~~~~

When running the algorithm as a pure Python process or as a Docker container
without further PostgreSQL deployment, the algorithm can use a SQLite database
for local storage.

For this purpose, the option ``--sqlite-file`` can be used to specify the path
to the SQLite database file. The SQLite database is created automatically if it
does not exist.

Alternatively, the ``KRAKEN_RUN_SQLITE_FILE`` environment variable can be used
to specify the path to the SQLite database file.

.. NOTE:: Do not use ``:memory:`` for an in-memory database, as this will
          result in data loss when the algorithm is restarted.
