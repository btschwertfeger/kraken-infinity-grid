#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2023 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

import sys
from logging import DEBUG, INFO, WARNING, basicConfig, getLogger
from typing import Any

from click import BOOL, FLOAT, INT, STRING, Context, echo, pass_context
from cloup import Choice, HelpFormatter, HelpTheme, Style, group, option, option_group
from cloup.constraints import If, accept_none, require_all


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
        ctx.fail(f"Value for option '{param.name}' must be larger than 0!")
    return value


def ensure_larger_equal_zero(
    ctx: Context,
    param: Any,  # noqa: ANN401
    value: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Ensure the value is larger than 0"""
    if value is not None and value < 0:
        ctx.fail(f"Value for option '{param.name}' must be larger then or equal to 0!")
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
    "--strategy",
    type=Choice(choices=("cDCA", "GridHODL", "GridSell", "SWING"), case_sensitive=True),
    help="The strategy to run.",
    required=True,
)
@option(
    "--name",
    required=True,
    type=STRING,
    help="""
    The name of the instance. Can be any name that is used to differentiate
    between instances of the kraken-infinity-grid.
    """,
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
    help="""
    The number of concurrent open buy orders e.g., ``5``. The number of
    always open buy positions specifies how many buy positions should be
    open at the same time. If the interval is defined to 2%, a number of 5
    open buy positions ensures that a rapid price drop of almost 10% that
    can be caught immediately.
    """,
)
@option(
    "--telegram-token",
    required=False,
    type=STRING,
    help="The Telegram token to use.",
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
    help="""
    The maximum investment, e.g. 1000 USD that the algorithm will manage.
    """,
)
@option(
    "--userref",
    required=True,
    type=INT,
    callback=ensure_larger_than_zero,
    help="""
    A reference number to identify the algorithm's orders. This can be a
    timestamp or any integer number. Use different userref's for different
    instances!
    """,
)
@option(
    "--fee",
    type=FLOAT,
    required=False,
    callback=ensure_larger_equal_zero,
    help="""
    The fee percentage to respect, e.g. '0.0026' for 0.26 %. This value does not
    change the actual paid fee, instead it used to estimate order sizes. If not
    passed, the highest maker fee will be used.
    """,
)
@option(
    "--sqlite-file",
    type=STRING,
    help="SQLite file to use as database.",
)
@option(
    "--db-name",
    type=STRING,
    default="kraken_infinity_grid",
    help="The database name.",
)
@option_group(
    "PostgreSQL Database Options",
    option(
        "--db-user",
        type=STRING,
        help="PostgreSQL DB user",
    ),
    option(
        "--db-password",
        type=STRING,
        help="PostgreSQL DB password",
    ),
    option(
        "--db-host",
        type=STRING,
        help="PostgreSQL DB host",
    ),
    option(
        "--db-port",
        type=STRING,
        help="PostgreSQL DB port",
    ),
    constraint=If(
        "sqlite_file",
        then=accept_none,
        else_=require_all,
    ),
)
@pass_context
def run(ctx: Context, **kwargs: dict) -> None:
    """Run the trading algorithm using the specified options."""
    # pylint: disable=import-outside-top-level
    import asyncio  # noqa: PLC0415
    import traceback  # noqa: PLC0415

    from kraken_infinity_grid.gridbot import KrakenInfinityGridBot  # noqa: PLC0415

    db_config = {
        "sqlite_file": kwargs.pop("sqlite_file"),
        "db_user": kwargs.pop("db_user"),
        "db_password": kwargs.pop("db_password"),
        "db_host": kwargs.pop("db_host"),
        "db_port": kwargs.pop("db_port"),
        "db_name": kwargs.pop("db_name"),
    }
    ctx.obj |= kwargs

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
        print("Not canceling unless '-f' was passed!")  # noqa: T201
        sys.exit(1)

    from pprint import pprint  # noqa: PLC0415

    from kraken.spot import Trade  # noqa: PLC0415

    trade = Trade(key=ctx.obj["api_key"], secret=ctx.obj["secret_key"])
    pprint(trade.cancel_all_orders())  # noqa: T203
