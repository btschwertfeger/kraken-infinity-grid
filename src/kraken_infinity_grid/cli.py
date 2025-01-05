#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2023 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

import sys
from logging import DEBUG, INFO, WARNING, basicConfig, getLogger
from typing import Any

from click import BOOL, FLOAT, INT, STRING, Context, echo, pass_context
from cloup import Choice, HelpFormatter, HelpTheme, Style, group, option


def print_version(ctx: Context, param: Any, value: Any) -> None:  # noqa: ANN401, ARG001
    """Prints the version of the package"""
    if not value or ctx.resilient_parsing:
        return
    from importlib.metadata import (  # noqa: PLC0415 # pylint: disable=import-outside-toplevel
        version,
    )

    echo(version("kraken-infinity-grid"))
    ctx.exit()


def ensure_larger_than_zero(
    ctx: Context,
    param: Any,  # noqa: ANN401
    value: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Ensure the value is larger than 0"""
    if value <= 0:
        ctx.fail(f"Value for option '{param.name}' must be larger than 0")
    return value


@group(
    context_settings={
        "auto_envvar_prefix": "KRAKEN",
        "help_option_names": ["-h", "--help"],
    },
    formatter_settings=HelpFormatter.settings(
        theme=HelpTheme(
            invoked_command=Style(fg="bright_yellow"),
            heading=Style(fg="bright_white", bold=True),
            constraint=Style(fg="magenta"),
            col1=Style(fg="bright_yellow"),
        ),
    ),
    no_args_is_help=True,
)
@option(
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
)
@option(
    "--api-key",
    required=True,
    help="The Kraken Spot API key",
    type=STRING,
)
@option(
    "--secret-key",
    required=True,
    type=STRING,
    help="The Kraken Spot API secret key",
)
@option(
    "-v",
    "--verbose",
    count=True,
    help="Increase the verbosity of output. Use -vv for even more verbosity.",
)
@option(
    "--dry-run",
    required=False,
    is_flag=True,
    default=False,
    help="Enable dry-run mode which do not execute trades.",
)
@pass_context
def cli(ctx: Context, **kwargs: dict) -> None:
    """
    Command-line interface entry point
    """
    ctx.ensure_object(dict)
    ctx.obj |= kwargs

    verbosity = kwargs.get("verbose", 0)

    basicConfig(
        format="%(asctime)s %(levelname)8s | %(message)s",
        datefmt="%Y/%m/%d %H:%M:%S",
        level=INFO if verbosity == 0 else DEBUG,
    )

    getLogger("requests").setLevel(WARNING)
    getLogger("urllib3").setLevel(WARNING)
    getLogger("websockets").setLevel(WARNING)

    if verbosity > 1:  # type: ignore[operator]
        getLogger("requests").setLevel(DEBUG)
        getLogger("websockets").setLevel(DEBUG)
        getLogger("kraken").setLevel(DEBUG)
    else:
        getLogger("websockets").setLevel(WARNING)
        getLogger("kraken").setLevel(WARNING)


@cli.command(
    context_settings={
        "auto_envvar_prefix": "KRAKEN_RUN",
        "help_option_names": ["-h", "--help"],
    },
    formatter_settings=HelpFormatter.settings(
        theme=HelpTheme(
            invoked_command=Style(fg="bright_yellow"),
            heading=Style(fg="bright_white", bold=True),
            constraint=Style(fg="magenta"),
            col1=Style(fg="bright_yellow"),
        ),
    ),
)
@option(
    "--name",
    required=True,
    type=STRING,
    help="The name of the bot.",
)
@option(
    "--base-currency",
    required=True,
    type=STRING,
    help="The base currency.",
)
@option(
    "--quote-currency",
    required=True,
    type=STRING,
    help="The quote currency.",
)
@option(
    "--amount-per-grid",
    required=True,
    type=FLOAT,
    help="The quote amount to use per interval.",
)
@option(
    "--interval",
    required=True,
    type=FLOAT,
    default=0.04,
    callback=ensure_larger_than_zero,
    help="The interval between orders.",
)
@option(
    "--n-open-buy-orders",
    required=True,
    type=INT,
    default=3,
    callback=ensure_larger_than_zero,
    help="The number of concurrent open buy orders.",
)
@option(
    "--cancel-all-open-buy-orders",
    required=True,
    type=BOOL,
    default=False,
    is_flag=True,
    help="Cancel all open buy orders on start.",
)
@option(
    "--telegram-token",
    required=False,
    type=STRING,
    help="The telegram token to use.",
)
@option(
    "--telegram-chat-id",
    required=False,
    type=STRING,
    help="The telegram chat ID to use.",
)
@option(
    "--exception-token",
    required=False,
    type=STRING,
    help="The telegram token to use for exceptions.",
)
@option(
    "--exception-chat-id",
    required=False,
    type=STRING,
    help="The telegram chat ID to use for exceptions.",
)
@option(
    "--max-investment",
    required=False,
    type=FLOAT,
    default=10e10,
    callback=ensure_larger_than_zero,
    help="The maximum quote investment of this bot.",
)
@option(
    "--userref",
    required=True,
    type=INT,
    callback=ensure_larger_than_zero,
    help="A reference number to identify the bots orders with.",
)
@option(
    "--db-user",
    type=STRING,
    help="PostgreSQL DB user",
    required=True,
)
@option(
    "--db-password",
    type=STRING,
    help="PostgreSQL DB password",
    required=True,
)
@option(
    "--db-name",
    type=STRING,
    default="kraken_infinity_grid",
    help="PostgreSQL DB name",
    required=True,
)
@option(
    "--db-host",
    type=STRING,
    default="postgresql",
    help="PostgreSQL DB host",
    required=True,
)
@option(
    "--db-port",
    type=STRING,
    default="5432",
    help="PostgreSQL DB port",
    required=True,
)
@option(
    "--strategy",
    type=Choice(choices=("DCA", "GridHODL", "GridSell", "SWING"), case_sensitive=True),
    help="The strategy to run.",
    required=True,
)
@pass_context
def run(ctx: Context, **kwargs: dict) -> None:
    """Run the trading algorithm using the specified options"""
    # pylint: disable=import-outside-top-level
    import asyncio  # noqa: PLC0415
    import traceback  # noqa: PLC0415

    from kraken_infinity_grid.gridbot import KrakenInfinityGridBot  # noqa: PLC0415

    ctx.obj |= kwargs
    db_config = {key: value for key, value in kwargs.items() if key.startswith("db_")}

    for key in db_config:
        del kwargs[key]

    async def main() -> None:
        # Instantiate the trading algorithm
        gridbot = KrakenInfinityGridBot(
            key=ctx.obj.pop("api_key"),
            secret=ctx.obj.pop("secret_key"),
            dry_run=ctx.obj.pop("dry_run"),
            config=kwargs,
            db_config=db_config,
        )

        try:
            await gridbot.run()
        except KeyboardInterrupt as exc:
            gridbot.save_exit(
                reason=f"Exception in top-run: {exc} {traceback.format_exc()}",
            )
            sys.exit(1)

    asyncio.run(main())


@cli.command(
    context_settings={
        "auto_envvar_prefix": "KRAKEN_CANCEL",
        "help_option_names": ["-h", "--help"],
    },
    formatter_settings=HelpFormatter.settings(
        theme=HelpTheme(
            invoked_command=Style(fg="bright_yellow"),
            heading=Style(fg="bright_white", bold=True),
            constraint=Style(fg="magenta"),
            col1=Style(fg="bright_yellow"),
        ),
    ),
)
@option(
    "-f",
    "--force",
    required=False,
    type=BOOL,
    default=False,
    is_flag=True,
    show_default=True,
)
@pass_context
def cancel(ctx: Context, **kwargs: dict) -> None:
    """Cancel all open orders."""
    ctx.obj |= kwargs
    if not ctx.obj["force"]:
        print("Not canceling -f is required!")  # noqa: T201
        sys.exit(1)

    from pprint import pprint  # noqa: PLC0415

    from kraken.spot import Trade  # noqa: PLC0415

    trade = Trade(key=ctx.obj["api_key"], secret=ctx.obj["secret_key"])
    pprint(trade.cancel_all_orders())  # noqa: T203
