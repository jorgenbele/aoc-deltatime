"""
Usage: aoc-dt [--update] [options]

Options:
  -r, --ranking                     Show scores ranked by delta time
  -t, --total                       Show total scores
  -y, --year YEAR                   The year to use
  -l, --leaderboard LEADERBOARD_ID  The leaderboard ID
  -c, --cookie COOKIE               The AOC cookie
  -f, --file FILE                   Use custom AOC json result file
  -v, --verbose                     Enable verbose output
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from docopt import docopt
from rich import print as rprint
from rich.console import Console
from rich.table import Table
from typing import Any, Dict, List, Optional

import humanize
import json
import os
import requests
import sys
import time
import re


@dataclass
class Flags:
    year: int
    json_path: str

    update: bool
    show_ranking: bool
    show_total: bool
    leaderboard_id: str
    cookie: str


@dataclass
class Member:
    id: str
    name: str
    score: Any
    stars: Any
    days: Any
    sum_dt: Optional[int]
    avg_dt: Optional[float]


@dataclass
class AOCData:
    year: int
    members: Dict[str, Member]
    days_dt: Dict[str, Any]
    last_day: int

    def ranked_days_dt(self, day):
        return sorted(list(self.days_dt[day].items()), key=lambda x: x[1])


console = Console()


def display_table(header, rows, justify_right=None):
    if justify_right == None:
        justify_right = []
    table = Table(show_header=True, header_style="bold blue")
    list(
        map(
            lambda ih: table.add_column(
                ih[1], justify=("right" if ih[0] in justify_right else None)
            ),
            enumerate(header),
        )
    )
    list(map(lambda r: table.add_row(*r), rows))
    console.print(table)


def parse_data(d: Dict[Any, Any]) -> AOCData:
    year = d["event"]
    last_day = 1

    members = {}
    days_dt: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(lambda: {}))
    for member_id, member_data in d["members"].items():
        member = Member(
            id=member_id,
            name=member_data["name"],
            score=member_data["local_score"],
            stars=member_data["stars"],
            days={},
            sum_dt=None,
            avg_dt=None,
        )
        sum_dt = 0
        count = 0
        for day, day_data in member_data["completion_day_level"].items():
            last_day = max(last_day, int(day))
            delta_time = (
                day_data.get("2", {"get_star_ts": 0})["get_star_ts"]
                - day_data["1"]["get_star_ts"]
            )
            if "2" in day_data:
                sum_dt += delta_time
                count += 1
            member.days[day] = {
                "delta_time": delta_time,
                "first_complete": day_data["1"]["get_star_ts"],
                "second_complete": day_data.get("2", {"get_star_ts": 0}),
            }
            days_dt[day][member_id] = delta_time

        if count == 0:
            average_dt = -1.0
        else:
            average_dt = sum_dt / count
        member.avg_dt = average_dt
        member.sum_dt = sum_dt
        members[member_id] = member

    return AOCData(year=year, members=members, days_dt=days_dt, last_day=last_day)


def update_if_possible(flags: Flags):
    try:
        last_modified = os.path.getmtime(flags.json_path)
        now = time.time()
        diff = now - last_modified
        if diff < 15 * 60:
            rprint("[bold red]Refusing to update, modified time too recent")
            return True  # already exists file
    except FileNotFoundError:
        pass

    r = requests.get(
        f"https://adventofcode.com/{flags.year}/leaderboard/private/view/{flags.leaderboard_id}.json",
        cookies={"session": flags.cookie},
    )
    if not r.ok:
        rprint(f"[bold red]{r}")  # TODO: warning
        return False

    data = r.json()
    with open(flags.json_path, "w") as f:
        json.dump(data, f)
        rprint(f"[bold green]Wrote updated score file to {flags.json_path}")
    return True


def format_dt(dt: int):
    if dt > 60 * 60 * 24:
        return ">24h"
    s = dt % 60
    m = ((dt - s) % (60 * 60)) // 60
    h = ((dt - s - m * 60) % (60 * 60 * 60)) // 3600
    d = ((dt - s - m * 60 - h * 60) % (60 * 60 * 60 * 24)) // (3600 * 24)
    out = ""
    if d > 0:
        out += f"{d}d"
    if h > 0:
        out += f"{h}h"
    if m > 0:
        out += f"{m}m"
    if s > 0:
        out += f"{s}s"
    return out


def display_ranking(data: AOCData):
    last_day = max(map(lambda x: int(x), data.days_dt.keys()))
    header = ["Name", "Delta time", "Points"]
    regex = re.compile("(second[s]|minute[s]|hour[s])")
    for day in range(1, last_day + 1):
        rprint(f"[bold] Day {day}")  # TODO: bold
        rows = [
            [
                data.members[member_id].name,
                format_dt(dt),
                str(len(data.members) - rank),
            ]
            for rank, (member_id, dt) in enumerate(data.ranked_days_dt(str(day)))
            if len(data.members) - rank > 0
        ]
        display_table(header, rows, justify_right=[2])


def display_total(data: AOCData):
    total_points: Dict[str, int] = defaultdict(lambda: 0)
    for day in range(1, data.last_day + 1):
        scores = sorted(list(data.days_dt[str(day)].items()), key=lambda x: x[1])
        for rank, (member_id, dt) in enumerate(scores):
            total_points[member_id] += len(data.members) - rank

    id_points_ordered = sorted(list(total_points.items()), key=lambda x: -x[1])
    header = ["Name", "Total Points"]
    rows = [
        [data.members[member_id].name, str(points)]
        for member_id, points in id_points_ordered
    ]
    display_table(header, rows)


def run(flags: Flags):

    if flags.update:
        with console.status("[bold green]Fetching data...") as status:
            assert update_if_possible(flags), "Unable to fetch data from API"

    with open(flags.json_path) as f:
        data = json.load(f)
    data = parse_data(data)

    if flags.show_ranking:
        display_ranking(data)

    if flags.show_total:
        display_total(data)


def main():
    args = docopt(__doc__, sys.argv[1:])
    verbose = args.get("--verbose", False)
    if verbose:
        print(args)

    year = args.get("--year") or datetime.now().year
    update = args.get("--update", False)

    leaderboard_id = args.get("--leaderboard") or os.environ.get("AOC_LEADERBOARD_ID")
    assert leaderboard_id
    cookie = args.get("--cookie") or os.environ.get("AOC_COOKIE")
    assert cookie

    json_path = args.get("--file") or f"{year}_{leaderboard_id}.json"
    show_ranking = args.get("--ranking", False)
    show_total = args.get("--total", False)

    flags = Flags(
        json_path=json_path,
        year=year,
        show_ranking=show_ranking,
        show_total=show_total,
        update=update,
        cookie=cookie,
        leaderboard_id=leaderboard_id,
    )
    run(flags)


if __name__ == "__main__":
    main()
