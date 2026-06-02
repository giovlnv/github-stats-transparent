#!/usr/bin/python3

import os
from typing import Dict, Optional, Set

import aiohttp


class Stats:
    def __init__(
        self,
        username: str,
        token: str,
        session: aiohttp.ClientSession,
        exclude_repos: Optional[Set] = None,
        exclude_langs: Optional[Set] = None,
    ):
        self.username = username
        self.token = token
        self.session = session
        self.exclude_repos = exclude_repos or set()
        self.exclude_langs = exclude_langs or set()

        self.languages: Dict[str, Dict] = {}
        self.repos = set()

    async def fetch(self) -> None:
        query = """
        query {
          viewer {
            repositories(first: 100, isFork: false) {
              nodes {
                nameWithOwner
                languages(first: 10) {
                  edges {
                    size
                    node {
                      name
                      color
                    }
                  }
                }
              }
            }
          }
        }
        """

        headers = {"Authorization": f"Bearer {self.token}"}

        async with self.session.post(
            "https://api.github.com/graphql",
            json={"query": query},
            headers=headers,
        ) as r:
            data = await r.json()

        repos = data["data"]["viewer"]["repositories"]["nodes"]

        for repo in repos:
            name = repo["nameWithOwner"]

            if name in self.exclude_repos:
                continue

            self.repos.add(name)

            for lang in repo["languages"]["edges"]:
                lang_name = lang["node"]["name"]

                if lang_name in self.exclude_langs:
                    continue

                if lang_name not in self.languages:
                    self.languages[lang_name] = {
                        "size": 0,
                        "color": lang["node"]["color"] or "#000000",
                    }

                self.languages[lang_name]["size"] += lang["size"]

        total = sum(v["size"] for v in self.languages.values()) or 1

        for v in self.languages.values():
            v["prop"] = (v["size"] / total) * 100