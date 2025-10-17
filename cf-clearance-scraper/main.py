from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Final, Iterable, List, Optional

import latest_user_agents
import user_agents
import zendriver
from selenium_authenticated_proxy import SeleniumAuthenticatedProxy
from zendriver import cdp
from zendriver.cdp.emulation import UserAgentBrandVersion, UserAgentMetadata
from zendriver.cdp.network import T_JSON_DICT, Cookie
from zendriver.core.element import Element

COMMAND: Final[str] = (
    '{name}: {binary} --header "Cookie: {cookies}" --header "User-Agent: {user_agent}" {url}'
)


def get_chrome_user_agent() -> str:
    """
    Get a random up-to-date Chrome user agent string.

    Returns
    -------
    str
        The user agent string.
    """
    chrome_user_agents = [
        user_agent
        for user_agent in latest_user_agents.get_latest_user_agents()
        if "Chrome" in user_agent and "Edg" not in user_agent
    ]

    return random.choice(chrome_user_agents)


class ChallengePlatform(Enum):
    """Cloudflare challenge platform types."""

    JAVASCRIPT = "non-interactive"
    MANAGED = "managed"
    INTERACTIVE = "interactive"


class CloudflareSolver:
    """
    A class for solving Cloudflare challenges with Zendriver.

    Parameters
    ----------
    user_agent : Optional[str]
        The user agent string to use for the browser requests.
    timeout : float
        The timeout in seconds to use for browser actions and solving challenges.
    http2 : bool
        Enable or disable the usage of HTTP/2 for the browser requests.
    http3 : bool
        Enable or disable the usage of HTTP/3 for the browser requests.
    headless : bool
        Enable or disable headless mode for the browser (not supported on Windows).
    proxy : Optional[str]
        The proxy server URL to use for the browser requests.
    """

    def __init__(
        self,
        *,
        user_agent: Optional[str],
        timeout: float,
        http2: bool,
        http3: bool,
        headless: bool,
        proxy: Optional[str],
    ) -> None:
        config = zendriver.Config(headless=headless)

        if user_agent is not None:
            config.add_argument(f"--user-agent={user_agent}")

        if not http2:
            config.add_argument("--disable-http2")

        if not http3:
            config.add_argument("--disable-quic")

        # 固定窗口大小与位置，便于坐标点击的一致性
        # 使用 Chrome 启动参数实现窗口尺寸与位置固定
        config.add_argument("--window-size=1920,1080")
        config.add_argument("--window-position=0,0")

        auth_proxy = SeleniumAuthenticatedProxy(proxy)
        auth_proxy.enrich_chrome_options(config)

        self.driver = zendriver.Browser(config)
        self._timeout = timeout

    async def __aenter__(self) -> CloudflareSolver:
        await self.driver.start()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.driver.stop()

    @staticmethod
    def _format_cookies(cookies: Iterable[Cookie]) -> List[T_JSON_DICT]:
        """
        Format cookies into a list of JSON cookies.

        Parameters
        ----------
        cookies : Iterable[Cookie]
            List of cookies.

        Returns
        -------
        List[T_JSON_DICT]
            List of JSON cookies.
        """
        return [cookie.to_json() for cookie in cookies]

    @staticmethod
    def extract_clearance_cookie(
        cookies: Iterable[T_JSON_DICT],
    ) -> Optional[T_JSON_DICT]:
        """
        Extract the Cloudflare clearance cookie from a list of cookies.

        Parameters
        ----------
        cookies : Iterable[T_JSON_DICT]
            List of cookies.

        Returns
        -------
        Optional[T_JSON_DICT]
            The Cloudflare clearance cookie. Returns None if the cookie is not found.
        """

        for cookie in cookies:
            if cookie["name"] == "cf_clearance":
                return cookie

        return None

    async def get_user_agent(self) -> str:
        """
        Get the current user agent string.

        Returns
        -------
        str
            The user agent string.
        """
        return await self.driver.main_tab.evaluate("navigator.userAgent")

    async def get_cookies(self) -> List[T_JSON_DICT]:
        """
        Get all cookies from the current page.

        Returns
        -------
        List[T_JSON_DICT]
            List of cookies.
        """
        return self._format_cookies(await self.driver.cookies.get_all())

    async def set_user_agent_metadata(self, user_agent: str) -> None:
        """
        Set the user agent metadata for the browser.

        Parameters
        ----------
        user_agent : str
            The user agent string to parse information from.
        """
        device = user_agents.parse(user_agent)

        metadata = UserAgentMetadata(
            architecture="x86",
            bitness="64",
            brands=[
                UserAgentBrandVersion(brand="Not)A;Brand", version="8"),
                UserAgentBrandVersion(
                    brand="Chromium", version=str(device.browser.version[0])
                ),
                UserAgentBrandVersion(
                    brand="Google Chrome",
                    version=str(device.browser.version[0]),
                ),
            ],
            full_version_list=[
                UserAgentBrandVersion(brand="Not)A;Brand", version="8"),
                UserAgentBrandVersion(
                    brand="Chromium", version=str(device.browser.version[0])
                ),
                UserAgentBrandVersion(
                    brand="Google Chrome",
                    version=str(device.browser.version[0]),
                ),
            ],
            mobile=device.is_mobile,
            model=device.device.model or "",
            platform=device.os.family,
            platform_version=device.os.version_string,
            full_version=device.browser.version_string,
            wow64=False,
        )

        self.driver.main_tab.feed_cdp(
            cdp.network.set_user_agent_override(
                user_agent, user_agent_metadata=metadata
            )
        )

    async def detect_challenge(self) -> Optional[ChallengePlatform]:
        """
        Detect the Cloudflare challenge platform on the current page.

        Returns
        -------
        Optional[ChallengePlatform]
            The Cloudflare challenge platform.
        """
        html = await self.driver.main_tab.get_content()

        for platform in ChallengePlatform:
            if f"cType: '{platform.value}'" in html:
                return platform

        return None

    async def solve_challenge(self) -> None:
        """Solve the Cloudflare challenge on the current page."""
        start_timestamp = datetime.now()

        while (
            self.extract_clearance_cookie(await self.get_cookies()) is None
            and await self.detect_challenge() is not None
            and (datetime.now() - start_timestamp).seconds < self._timeout
        ):
            # 使用屏幕坐标进行系统级点击，确保与截图坐标一致
            import ctypes
            x, y = 532, 375
            try:
                ctypes.windll.user32.SetCursorPos(int(x), int(y))
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # 左键按下
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # 左键抬起
            except Exception:
                pass

            # 频率：每秒一次
            await asyncio.sleep(1.0)

            # 每次点击后检查是否已经下发 cf_clearance
            if self.extract_clearance_cookie(await self.get_cookies()) is not None:
                break


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="A simple program for scraping Cloudflare clearance (cf_clearance) cookies from websites issuing Cloudflare challenges to visitors"
    )

    parser.add_argument(
        "url",
        metavar="URL",
        help="The URL to scrape the Cloudflare clearance cookie from",
        type=str,
    )

    parser.add_argument(
        "-f",
        "--file",
        default=None,
        help="The file to write the Cloudflare clearance cookie information to, in JSON format",
        type=str,
    )

    parser.add_argument(
        "-t",
        "--timeout",
        default=30,
        help="The timeout in seconds to use for solving challenges",
        type=float,
    )

    parser.add_argument(
        "-p",
        "--proxy",
        default=None,
        help="The proxy server URL to use for the browser requests",
        type=str,
    )

    parser.add_argument(
        "-ua",
        "--user-agent",
        default=None,
        help="The user agent to use for the browser requests",
        type=str,
    )

    parser.add_argument(
        "--disable-http2",
        action="store_true",
        help="Disable the usage of HTTP/2 for the browser requests",
    )

    parser.add_argument(
        "--disable-http3",
        action="store_true",
        help="Disable the usage of HTTP/3 for the browser requests",
    )

    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run the browser in headed mode",
    )

    parser.add_argument(
        "-ac",
        "--all-cookies",
        action="store_true",
        help="Retrieve all cookies from the page, not just the Cloudflare clearance cookie",
    )

    parser.add_argument(
        "-c",
        "--curl",
        action="store_true",
        help="Get the cURL command for the request with the cookies and user agent",
    )

    parser.add_argument(
        "-w",
        "--wget",
        action="store_true",
        help="Get the Wget command for the request with the cookies and user agent",
    )

    parser.add_argument(
        "-a",
        "--aria2",
        action="store_true",
        help="Get the aria2 command for the request with the cookies and user agent",
    )

    args = parser.parse_args()

    logging.basicConfig(
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )

    logging.getLogger("zendriver").setLevel(logging.WARNING)
    logging.info("Launching %s browser...", "headed" if args.headed else "headless")

    challenge_messages = {
        ChallengePlatform.JAVASCRIPT: "Solving Cloudflare challenge [JavaScript]...",
        ChallengePlatform.MANAGED: "Solving Cloudflare challenge [Managed]...",
        ChallengePlatform.INTERACTIVE: "Solving Cloudflare challenge [Interactive]...",
    }

    user_agent = get_chrome_user_agent() if args.user_agent is None else args.user_agent

    async with CloudflareSolver(
        user_agent=user_agent,
        timeout=args.timeout,
        http2=not args.disable_http2,
        http3=not args.disable_http3,
        headless=not args.headed,
        proxy=args.proxy,
    ) as solver:
        logging.info("Going to %s...", args.url)

        try:
            await solver.driver.get(args.url)
        except asyncio.TimeoutError as err:
            logging.error(err)
            return

        all_cookies = await solver.get_cookies()
        clearance_cookie = solver.extract_clearance_cookie(all_cookies)

        if clearance_cookie is None:
            await solver.set_user_agent_metadata(await solver.get_user_agent())
            challenge_platform = await solver.detect_challenge()

            if challenge_platform is None:
                logging.error("No Cloudflare challenge detected.")
                return

            logging.info(challenge_messages[challenge_platform])
            await solver.solve_challenge()

            all_cookies = await solver.get_cookies()
            clearance_cookie = solver.extract_clearance_cookie(all_cookies)

        if clearance_cookie is None:
            logging.error("Failed to retrieve the Cloudflare clearance cookie. Try again.")
            return

        logging.info("Retrieved the Cloudflare clearance cookie!")
        logging.info(
            COMMAND.format(
                name="curl",
                binary="curl",
                cookies="; ".join(
                    f"{cookie['name']}={cookie['value']}" for cookie in await solver.driver.cookies.get_all()
                ),
                user_agent=await solver.get_user_agent(),
                url=args.url,
            )
        )

        now = datetime.now(timezone.utc)

        expires = datetime.fromtimestamp(clearance_cookie["expires"] / 1000, timezone.utc)
        delta = expires - now

        if delta.days > 1:
            expires_str = expires.strftime("%B %d, %Y at %H:%M %p %Z")
        else:
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            expires_str = f"{hours} hours, {minutes} minutes and {seconds} seconds"

        additional_cookies = [cookie.to_json() for cookie in await solver.driver.cookies.get_all()]

        data: Dict[str, Any] = {
            args.url: [
                {
                    "cookies": [clearance_cookie],
                    "user_agent": await solver.get_user_agent(),
                    "expires": expires_str,
                },
                {
                    "cookies": additional_cookies,
                    "user_agent": await solver.get_user_agent(),
                    "expires": expires_str,
                },
            ]
        }

        if args.file is not None:
            with open(args.file, "w") as file:
                json.dump(data, file)

        if args.all_cookies:
            _cookies = [cookie.to_json_dict() for cookie in await solver.driver.cookies.get_all()]

            data = {
                args.url: [
                    {
                        "cookies": _cookies,
                        "user_agent": await solver.get_user_agent(),
                        "expires": expires_str,
                    }
                ]
            }

            print(json.dumps(data))

        if args.curl:
            print(
                COMMAND.format(
                    name="curl",
                    binary="curl",
                    cookies="; ".join(
                        f"{cookie['name']}={cookie['value']}" for cookie in await solver.driver.cookies.get_all()
                    ),
                    user_agent=await solver.get_user_agent(),
                    url=args.url,
                )
            )

        if args.wget:
            print(
                COMMAND.format(
                    name="Wget",
                    binary="wget",
                    cookies="; ".join(
                        f"{cookie['name']}={cookie['value']}" for cookie in await solver.driver.cookies.get_all()
                    ),
                    user_agent=await solver.get_user_agent(),
                    url=args.url,
                )
            )

        if args.aria2:
            print(
                COMMAND.format(
                    name="aria2",
                    binary="aria2c",
                    cookies="; ".join(
                        f"{cookie['name']}={cookie['value']}" for cookie in await solver.driver.cookies.get_all()
                    ),
                    user_agent=await solver.get_user_agent(),
                    url=args.url,
                )
            )

if __name__ == "__main__":
    asyncio.run(main())
