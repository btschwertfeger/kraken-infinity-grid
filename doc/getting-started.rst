.. -*- coding: utf-8 -*-
.. Copyright (C) 2025 Benjamin Thomas Schwertfeger
.. GitHub: https://github.com/btschwertfeger
..

.. _getting-started-section:

Getting Started
===============

Before installing and running the `kraken-infinity-grid`_ package, you need to
make sure to clearly understand the available trading strategies and their
configuration. Avoid running the algorithm with real money before you are
confident in the algorithm's behavior and performance!

Preparation
-----------

1. In order to trade at the `Kraken`_ Cryptocurrency Exchange, you need to
   generate API keys for the Kraken exchange. You can do this by following the
   instructions on the `Kraken`_ website. Make sure to generate keys with the
   required permissions for trading and querying orders.

2. The algorithm leverages Telegram Bots to send notifications about the current
   state of the algorithm. We need two telegram bots, one for the notifications
   about the algorithm's state and trades and one for notifications about
   errors.

   - Create two bots, name as you wish via: https://telegram.me/BotFather.
   - Start the chat with both new telegram bots.
   - Get the bot token from the BotFather and access
     ``https://api.telegram.org/bot<your bot token here>/getUpdates`` to receive
     your chat ID.
   - Save the chat_id as well as the bot tokens for both of them, we'll need
     them later.

Running as pure Python process
------------------------------

1. Install the package via pip:

    .. code-block:: bash

        python3 -m venv venv
        source venv/bin/activate
        pip install kraken-infinity-grid

2. Run the algorithm via command-line while using a local sqlite database:

    .. code-block:: bash

        kraken-infinity-grid \
            --api-key <your-api-key> \
            --api-secret <your-api-secret> \
            --telegram-bot-token <your-telegram-bot-token> \
            --telegram-chat-id <your-telegram-chat-id> \
            run \
            ...
            --sqlite-file=/path/to/sqlite.db


.. _getting-started-docker-compose-section:

Running via Docker Compose
--------------------------

This repository of this project (`kraken-infinity-grid`_) contains a
``docker-compose.yaml`` file that can be used to run the algorithm using docker
compose. The ``docker-compose.yaml`` also provides a default configuration for
the PostgreSQL database. To run the algorithm, follow these steps:

1. Clone the repository:

   .. code-block:: bash

       git clone https://github.com/btschwertfeger/kraken-infinity-grid.git

2. Build the Docker images:

   .. code-block:: bash

       docker system prune -a
       docker compose build --no-cache

3. Configure the algorithm by either by ensuring the environment variables
   documented in the :ref:`Configuration <configuration-section>` section are
   set.

4. Run the algorithm:

   .. code-block:: bash

       docker compose up # -d


5. Check the logs of the container and the Telegram chat for updates.

.. NOTE:: In the future, there will be a Docker image available including
          kraken-infinity-grid.
