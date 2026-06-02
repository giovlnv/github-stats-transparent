#!/usr/bin/python3

import asyncio
import os
import re

import aiohttp

from github_stats import Stats


################################################################################
# Helper Functions
################################################################################

def generate_output_folder() -> None:
    """
    Create the output folder if it does not already exist
    """
    if not os.path.isdir("generated"):
        print("Creating generated directory...",
              flush=True)
        os.mkdir("generated")


################################################################################
# Individual Image Generation Functions
################################################################################

async def generate_overview(s: Stats) -> None:
    print("Before contributions",
          flush=True)
    print(await s.total_contributions)

    print("Before lines_changed",
          flush=True)
    """
    Generate an SVG badge with summary statistics
    :param s: Represents user's GitHub statistics
    """

    print("Starting overview generation...",
          flush=True)

    if not os.path.exists("templates/overview.svg"):
        raise FileNotFoundError(
            "templates/overview.svg not found"
        )

    with open("templates/overview.svg", "r", encoding="utf-8") as f:
        output = f.read()

    print("Calculating name...",
          flush=True)
    output = re.sub("{{ name }}", await s.name, output)

    print("Calculating stars...",
          flush=True)
    output = re.sub("{{ stars }}", f"{await s.stargazers:,}", output)

    print("Calculating forks...",
          flush=True)
    output = re.sub("{{ forks }}", f"{await s.forks:,}", output)

    print("Calculating contributions...",
          flush=True) 
    output = re.sub(
        "{{ contributions }}",
        f"{await s.total_contributions:,}",
        output
    )

    print("Calculating lines changed...",
          flush=True)
    lines_changed = await s.lines_changed

    changed = (
        lines_changed[0]
        + lines_changed[1]
    )

    output = re.sub(
        "{{ lines_changed }}",
        f"{changed:,}",
        output
    )

    print("Calculating views...",
          flush=True)
    output = re.sub(
        "{{ views }}",
        f"{await s.views:,}",
        output
    )

    print("Calculating repositories...",
          flush=True)
    output = re.sub(
        "{{ repos }}",
        f"{len(await s.all_repos):,}",
        output
    )

    generate_output_folder()

    with open("generated/overview.svg", "w", encoding="utf-8") as f:
        f.write(output)

    size = os.path.getsize("generated/overview.svg")

    print(
        f"generated/overview.svg written "
        f"({size} bytes)"
    )
    lines_changed = await s.lines_changed

    print("After lines_changed")

async def generate_languages(s: Stats) -> None:
    """
    Generate an SVG badge with summary languages used
    :param s: Represents user's GitHub statistics
    """

    print("Starting language generation...",
          flush=True)

    if not os.path.exists("templates/languages.svg"):
        raise FileNotFoundError(
            "templates/languages.svg not found"
        )

    with open("templates/languages.svg", "r", encoding="utf-8") as f:
        output = f.read()

    print("Calculating languages...", flush=True)

    progress = ""
    lang_list = ""

    sorted_languages = sorted(
        (await s.languages).items(),
        reverse=True,
        key=lambda t: t[1].get("size")
    )

    print(
        f"Found {len(sorted_languages)} languages"
    )

    delay_between = 150

    for i, (lang, data) in enumerate(sorted_languages):

        color = data.get("color")
        color = color if color is not None else "#000000"

        ratio = [.98, .02]

        if data.get("prop", 0) > 50:
            ratio = [.99, .01]

        if i == len(sorted_languages) - 1:
            ratio = [1, 0]

        progress += (
            f'<span style="background-color: {color};'
            f'width: {(ratio[0] * data.get("prop", 0)):0.3f}%;'
            f'margin-right: {(ratio[1] * data.get("prop", 0)):0.3f}%;" '
            f'class="progress-item"></span>'
        )

        lang_list += f"""
<li style="animation-delay: {i * delay_between}ms;">
<svg xmlns="http://www.w3.org/2000/svg" class="octicon" style="fill:{color};"
viewBox="0 0 16 16" version="1.1" width="16" height="16"><path
fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8z"></path></svg>
<span class="lang">{lang}</span>
<span class="percent">{data.get("prop", 0):0.2f}%</span>
</li>

"""

    output = re.sub(
        r"{{ progress }}",
        progress,
        output
    )

    output = re.sub(
        r"{{ lang_list }}",
        lang_list,
        output
    )

    generate_output_folder()

    with open("generated/languages.svg", "w", encoding="utf-8") as f:
        f.write(output)

    size = os.path.getsize("generated/languages.svg")

    print(
        f"generated/languages.svg written "
        f"({size} bytes)"
    )


################################################################################
# Main Function
################################################################################

async def main() -> None:
    """
    Generate all badges
    """

    print("Starting image generation...")

    access_token = os.getenv("ACCESS_TOKEN")

    if not access_token:
        raise Exception(
            "ACCESS_TOKEN is missing"
        )

    user = os.getenv("GITHUB_ACTOR")

    print(f"User: {user}")

    exclude_repos = os.getenv("EXCLUDED")

    exclude_repos = (
        {x.strip() for x in exclude_repos.split(",")}
        if exclude_repos
        else None
    )

    print(f"Excluded repos: {exclude_repos}")

    exclude_langs = os.getenv("EXCLUDED_LANGS")

    exclude_langs = (
        {x.strip() for x in exclude_langs.split(",")}
        if exclude_langs
        else None
    )

    print(f"Excluded languages: {exclude_langs}")

    consider_forked_repos = (
        os.getenv(
            "COUNT_STATS_FROM_FORKS",
            ""
        ).lower() == "true"
    )

    print(
        f"Count stats from forks: "
        f"{consider_forked_repos}"
    )

    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=30,
        sock_read=30
    )

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        s = Stats(
            user,
            access_token,
            session,
            exclude_repos=exclude_repos,
            exclude_langs=exclude_langs,
            consider_forked_repos=consider_forked_repos
        )

        await asyncio.gather(
            generate_languages(s),
            generate_overview(s)
        )

    print("\nGenerated files:")

    if os.path.exists("generated"):

        for root, _, files in os.walk("generated"):

            for file in files:

                print(
                    os.path.join(root, file)
                )

    else:

        print(
            "generated folder not found"
        )

    print(
        "\nImage generation completed."
    )


if __name__ == "__main__":
    asyncio.run(main())