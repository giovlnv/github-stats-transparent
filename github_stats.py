#!/usr/bin/python3

import asyncio
import os
from typing import Dict, List, Optional, Set

import aiohttp
import requests


###############################################################################
# Main Classes
###############################################################################

class Queries(object):
    """
    Class with functions to query the GitHub GraphQL (v4) API and the REST (v3)
    API. Also includes functions to dynamically generate GraphQL queries.
    """

    def __init__(self, username: str, access_token: str,
                 session: aiohttp.ClientSession, max_connections: int = 10):
        self.username = username
        self.access_token = access_token
        self.session = session
        self.semaphore = asyncio.Semaphore(max_connections)

    async def query(self, generated_query: str) -> Dict:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }

        try:
            async with self.semaphore:
                r = await self.session.post(
                    "https://api.github.com/graphql",
                    headers=headers,
                    json={"query": generated_query}
                )

            return await r.json()

        except Exception as e:
            print(f"GraphQL query failed: {e}", flush=True)

            async with self.semaphore:
                r = requests.post(
                    "https://api.github.com/graphql",
                    headers=headers,
                    json={"query": generated_query},
                    timeout=30
                )

            print(f"GraphQL fallback status: {r.status_code}", flush=True)
            return r.json()

    async def query_rest(self, path: str, params: Optional[Dict] = None) -> Dict:
        if params is None:
            params = dict()

        if path.startswith("/"):
            path = path[1:]

        delay = 1

        for attempt in range(3):
            headers = {
                "Authorization": f"token {self.access_token}",
            }

            try:
                async with self.semaphore:
                    r = await self.session.get(
                        f"https://api.github.com/{path}",
                        headers=headers,
                        params=tuple(params.items())
                    )

                remaining = r.headers.get("X-RateLimit-Remaining")

                print(
                    f"[Attempt {attempt + 1}] {path} -> HTTP {r.status} "
                    f"(rate remaining: {remaining})"
                )

                if r.status == 202:
                    print(f"{path} returned 202. Waiting {delay}s...")
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue

                if r.status != 200:
                    text = await r.text()
                    print(f"GitHub API returned {r.status} for {path}")
                    print(text[:500])
                    return {}

                result = await r.json()
                if result is not None:
                    return result

            except Exception as e:
                print(f"REST query failed for {path}: {e}", flush=True)

                try:
                    async with self.semaphore:
                        r = requests.get(
                            f"https://api.github.com/{path}",
                            headers=headers,
                            params=tuple(params.items()),
                            timeout=30
                        )

                    print(f"Fallback request {path} -> HTTP {r.status_code}")

                    if r.status_code == 200:
                        return r.json()

                except Exception as fallback_error:
                    print(f"Fallback request failed for {path}: {fallback_error}")

        print(f"Too many retries for {path}. Data incomplete.")
        return {}

    @staticmethod
    def repos_overview(contrib_cursor: Optional[str] = None,
                       owned_cursor: Optional[str] = None) -> str:
        return f"""{{
  viewer {{
    login,
    name,
    repositories(
        first: 100,
        orderBy: {{
            field: UPDATED_AT,
            direction: DESC
        }},
        isFork: false,
        after: {"null" if owned_cursor is None else '"' + owned_cursor + '"'}
    ) {{
      pageInfo {{
        hasNextPage
        endCursor
      }}
      nodes {{
        nameWithOwner
        stargazers {{
          totalCount
        }}
        forkCount
        languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{
          edges {{
            size
            node {{
              name
              color
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""

    @staticmethod
    def contrib_years() -> str:
        return """
query {
  viewer {
    contributionsCollection {
      contributionYears
    }
  }
}
"""

    @staticmethod
    def contribs_by_year(year: str) -> str:
        return f"""
    year{year}: contributionsCollection(
        from: "{year}-01-01T00:00:00Z",
        to: "{int(year) + 1}-01-01T00:00:00Z"
    ) {{
      contributionCalendar {{
        totalContributions
      }}
    }}
"""


class Stats(object):

    def __init__(self, username: str, access_token: str,
                 session: aiohttp.ClientSession,
                 exclude_repos: Optional[Set] = None,
                 exclude_langs: Optional[Set] = None,
                 consider_forked_repos: bool = False):

        self.username = username
        self._exclude_repos = set() if exclude_repos is None else exclude_repos
        self._exclude_langs = set() if exclude_langs is None else exclude_langs
        self._consider_forked_repos = consider_forked_repos
        self.queries = Queries(username, access_token, session)

        self._name = None
        self._stargazers = None
        self._forks = None
        self._total_contributions = None
        self._languages = None
        self._repos = None
        self._views = None

    async def to_str(self) -> str:
        languages = await self.languages_proportional
        formatted_languages = "\n  - ".join(
            [f"{k}: {v:0.4f}%" for k, v in languages.items()]
        )

        return f"""Name: {await self.name}
Stargazers: {await self.stargazers:,}
Forks: {await self.forks:,}
All-time contributions: {await self.total_contributions:,}
Repositories with contributions: {len(await self.all_repos)}
Project page views: {await self.views:,}
Languages:
  - {formatted_languages}"""

    async def get_stats(self) -> None:
        self._stargazers = 0
        self._forks = 0
        self._languages = {}
        self._repos = set()
        self._ignored_repos = set()

        next_owned = None
        next_contrib = None

        while True:
            raw_results = await self.queries.query(
                Queries.repos_overview(
                    owned_cursor=next_owned,
                    contrib_cursor=next_contrib
                )
            ) or {}

            viewer = raw_results.get("data", {}).get("viewer", {})

            self._name = viewer.get("name") or viewer.get("login", "No Name")

            repos_data = viewer.get("repositories", {})
            contrib_data = viewer.get("repositoriesContributedTo", {})

            repos = repos_data.get("nodes", [])

            if self._consider_forked_repos:
                repos += contrib_data.get("nodes", [])
            else:
                for repo in contrib_data.get("nodes", []):
                    self._ignored_repos.add(repo.get("nameWithOwner"))

            for repo in repos:
                name = repo.get("nameWithOwner")
                if name in self._repos or name in self._exclude_repos:
                    continue

                self._repos.add(name)
                self._stargazers += repo.get("stargazers", {}).get("totalCount", 0)
                self._forks += repo.get("forkCount", 0)

                for lang in repo.get("languages", {}).get("edges", []):
                    lang_name = lang.get("node", {}).get("name", "Other")

                    if lang_name in self._exclude_langs:
                        continue

                    if lang_name not in self._languages:
                        self._languages[lang_name] = {
                            "size": 0,
                            "occurrences": 0,
                            "color": lang.get("node", {}).get("color")
                        }

                    self._languages[lang_name]["size"] += lang.get("size", 0)
                    self._languages[lang_name]["occurrences"] += 1

            if repos_data.get("pageInfo", {}).get("hasNextPage") or \
               contrib_data.get("pageInfo", {}).get("hasNextPage"):
                next_owned = repos_data.get("pageInfo", {}).get("endCursor")
                next_contrib = contrib_data.get("pageInfo", {}).get("endCursor")
            else:
                break

        total = sum(v["size"] for v in self._languages.values())
        if total > 0:
            for v in self._languages.values():
                v["prop"] = 100 * v["size"] / total

    @property
    async def name(self) -> str:
        if self._name is None:
            await self.get_stats()
        return self._name

    @property
    async def stargazers(self) -> int:
        if self._stargazers is None:
            await self.get_stats()
        return self._stargazers

    @property
    async def forks(self) -> int:
        if self._forks is None:
            await self.get_stats()
        return self._forks

    @property
    async def languages(self) -> Dict:
        if self._languages is None:
            await self.get_stats()
        return self._languages

    @property
    async def languages_proportional(self) -> Dict:
        if self._languages is None:
            await self.get_stats()
        return {k: v.get("prop", 0) for k, v in self._languages.items()}

    @property
    async def repos(self) -> List[str]:
        if self._repos is None:
            await self.get_stats()
        return self._repos

    @property
    async def all_repos(self) -> List[str]:
        if self._repos is None:
            await self.get_stats()
        return self._repos | self._ignored_repos

    @property
    async def total_contributions(self) -> int:
        if self._total_contributions is not None:
            return self._total_contributions

        self._total_contributions = 0

        years = (await self.queries.query(Queries.contrib_years()))
        years = years.get("data", {}).get("viewer", {}).get(
            "contributionsCollection", {}
        ).get("contributionYears", [])

        by_year = (await self.queries.query(
            Queries.all_contribs(years)
        )).get("data", {}).get("viewer", {}).values()

        for year in by_year:
            self._total_contributions += year.get(
                "contributionCalendar", {}
            ).get("totalContributions", 0)

        return self._total_contributions

    @property
    async def views(self) -> int:
        if self._views is not None:
            return self._views

        total = 0

        for repo in await self.repos:
            r = await self.queries.query_rest(f"/repos/{repo}/traffic/views")
            for v in r.get("views", []):
                total += v.get("count", 0)

        self._views = total
        return total


async def main() -> None:
    access_token = os.getenv("ACCESS_TOKEN")
    user = os.getenv("GITHUB_ACTOR")

    timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        s = Stats(user, access_token, session)
        print(await s.to_str())


if __name__ == "__main__":
    asyncio.run(main())