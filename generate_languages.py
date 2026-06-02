#!/usr/bin/python3

import asyncio
import os
import re
import aiohttp

from github_stats import Stats


def ensure_folder():
    os.makedirs("generated", exist_ok=True)


async def generate():
    token = os.getenv("ACCESS_TOKEN")
    user = os.getenv("GITHUB_ACTOR")

    exclude_repos = os.getenv("EXCLUDED")
    exclude_repos = set(exclude_repos.split(",")) if exclude_repos else set()

    exclude_langs = os.getenv("EXCLUDED_LANGS")
    exclude_langs = set(exclude_langs.split(",")) if exclude_langs else set()

    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        s = Stats(user, token, session, exclude_repos, exclude_langs)
        await s.fetch()

        with open("templates/languages.svg", "r", encoding="utf-8") as f:
            svg = f.read()

        sorted_langs = sorted(
            s.languages.items(),
            key=lambda x: x[1]["size"],
            reverse=True,
        )

        progress = ""
        list_items = ""

        for lang, data in sorted_langs:
            color = data["color"]
            prop = data["prop"]

            progress += (
                f'<span style="background-color:{color};width:{prop:.3f}%" '
                f'class="progress-item"></span>'
            )

            list_items += f"""
<li>
<span class="lang">{lang}</span>
<span class="percent">{prop:.2f}%</span>
</li>
"""

        svg = re.sub("{{ progress }}", progress, svg)
        svg = re.sub("{{ lang_list }}", list_items, svg)

        ensure_folder()

        with open("generated/languages.svg", "w", encoding="utf-8") as f:
            f.write(svg)

        print("generated/languages.svg updated")


if __name__ == "__main__":
    asyncio.run(generate())