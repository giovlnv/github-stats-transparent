#!/usr/bin/python3

import asyncio
import os
import re
import aiohttp

from github_stats import Stats


def generate_output_folder() -> None:
    if not os.path.isdir("generated"):
        print("Creating generated directory...", flush=True)
        os.mkdir("generated")


async def generate_overview(s: Stats) -> None:
    print("Starting overview generation...", flush=True)

    with open("templates/overview.svg", "r", encoding="utf-8") as f:
        output = f.read()

    output = re.sub("{{ name }}", await s.name, output)
    output = re.sub("{{ stars }}", f"{await s.stargazers:,}", output)
    output = re.sub("{{ forks }}", f"{await s.forks:,}", output)
    output = re.sub("{{ contributions }}", f"{await s.total_contributions:,}", output)
    output = re.sub("{{ views }}", f"{await s.views:,}", output)
    output = re.sub("{{ repos }}", f"{len(await s.all_repos):,}", output)

    generate_output_folder()

    with open("generated/overview.svg", "w", encoding="utf-8") as f:
        f.write(output)

    print(
        f"generated/overview.svg written ({os.path.getsize('generated/overview.svg')} bytes)"
    )


async def generate_languages(s: Stats) -> None:
    print("Starting language generation...", flush=True)

    with open("templates/languages.svg", "r", encoding="utf-8") as f:
        output = f.read()

    sorted_languages = sorted(
        (await s.languages).items(),
        key=lambda t: t[1].get("size"),
        reverse=True
    )

    progress = ""
    lang_list = ""

    for i, (lang, data) in enumerate(sorted_languages):
        color = data.get("color") or "#000000"

        ratio = [.99, .01] if data.get("prop", 0) > 50 else [.98, .02]

        progress += (
            f'<span style="background-color:{color};'
            f'width:{data.get("prop", 0) * ratio[0]:.3f}%;" '
            f'class="progress-item"></span>'
        )

        lang_list += f"""
<li>
<span class="lang">{lang}</span>
<span class="percent">{data.get("prop", 0):.2f}%</span>
</li>
"""

    output = re.sub("{{ progress }}", progress, output)
    output = re.sub("{{ lang_list }}", lang_list, output)

    generate_output_folder()

    with open("generated/languages.svg", "w", encoding="utf-8") as f:
        f.write(output)

    print(
        f"generated/languages.svg written ({os.path.getsize('generated/languages.svg')} bytes)"
    )


async def main() -> None:
    print("Starting image generation...", flush=True)

    access_token = os.getenv("ACCESS_TOKEN")
    user = os.getenv("GITHUB_ACTOR")

    exclude_repos = os.getenv("EXCLUDED")
    exclude_repos = {x.strip() for x in exclude_repos.split(",")} if exclude_repos else None

    exclude_langs = os.getenv("EXCLUDED_LANGS")
    exclude_langs = {x.strip() for x in exclude_langs.split(",")} if exclude_langs else None

    consider_forks = os.getenv("COUNT_STATS_FROM_FORKS", "").lower() == "true"

    timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        s = Stats(
            user,
            access_token,
            session,
            exclude_repos=exclude_repos,
            exclude_langs=exclude_langs,
            consider_forked_repos=consider_forks
        )

        await asyncio.gather(
            generate_languages(s),
            generate_overview(s)
        )


if __name__ == "__main__":
    asyncio.run(main())