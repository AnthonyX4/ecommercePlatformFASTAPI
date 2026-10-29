import asyncio
import httpx
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent # Backend/, so .env and sneakers.json resolve the same regardless of cwd

load_dotenv(BACKEND_DIR / ".env") # loads the environment values from the environment file

api_key = os.getenv("API_KEY")
base_url = os.getenv("BASE_URL") # https://api.pckt.sh
if not api_key or not base_url:
    sys.exit(f"API_KEY and BASE_URL need to be set in {BACKEND_DIR / '.env'} before harvesting")

# pckt.sh cached StockX catalog (data at most 24h old, cheaper than the real-time endpoints), 0.4 credits per request each
search_url = base_url + "/v1/catalog/stockx/search"   # 15 results per page, but no gender or description
product_url = base_url + "/v1/catalog/stockx/product" # one product by id, has everything
# now that we have the values, let's begin harvesting

SEARCH_QUERIES = [ # a list instead of a set, so the queries run in the same order every time
    # Jordan
    "jordan 1 high", "jordan 1 low", "jordan 3", "jordan 4", "jordan 11",
    # Nike
    "nike dunk low", "nike sb dunk", "air force 1", "air max 1", "air max 90", "nike vomero",
    # adidas
    "adidas samba", "adidas gazelle", "adidas campus", "yeezy 350", "yeezy slide",
    # New Balance
    "new balance 550", "new balance 990", "new balance 2002r", "new balance 9060",
    # Others
    "asics gel kayano", "asics gel 1130", "salomon xt-6", "converse chuck 70", "vans old skool",
]

MAX_PAGES_PER_QUERY = 10 # the api only searches up to 10 pages of results
TARGET_SNEAKERS = 510 # a few over 500, in case some detail lookups fail
SECONDS_BETWEEN_REQUESTS = 1.1 # free plan is 1 request per second across all endpoints
MAX_REQUESTS = 650 # hard cap on credits spent per run (650 * 0.4 = 260 credits), search + details should need ~560

requests_made = 0


class StopHarvest(Exception):
    """The api refused us in a way that will keep happening (bad key, out of credits), stop asking."""


async def get_json(client: httpx.AsyncClient, url: str, params: dict):
    global requests_made
    if requests_made >= MAX_REQUESTS:
        raise StopHarvest(f"hit MAX_REQUESTS ({MAX_REQUESTS})")

    for attempt in range(3):
        await asyncio.sleep(SECONDS_BETWEEN_REQUESTS) # stay under the rate limit
        requests_made += 1
        response = await client.get(url, params=params)

        if response.status_code == 429: # too fast, back off and try again
            await asyncio.sleep(5 * (attempt + 1))
            continue
        if response.status_code in (401, 402, 403):
            raise StopHarvest(f"{response.status_code}: {response.text}")
        response.raise_for_status() # anything else that went wrong
        return response.json()

    raise StopHarvest("still rate limited after 3 tries")


async def search_sneakers(client: httpx.AsyncClient) -> dict:
    """Phase 1: search every query one page at a time (page 1 of all of them, then page 2...) so we get variety, not 150 Jordan 1s."""
    found = {}
    finished = set() # queries that ran out of results

    for page in range(1, MAX_PAGES_PER_QUERY + 1):
        for query in SEARCH_QUERIES:
            if query in finished:
                continue
            if len(found) >= TARGET_SNEAKERS:
                return found

            try:
                items = await get_json(client, search_url, {"query": query, "page": page, "market": "US"})
            except httpx.HTTPError as error:
                print(f"something has gone wrong searching {query} page {page}: {error}")
                finished.add(query) # if the query fails once, it will fail for the remaining pages too
                continue

            if not items:
                finished.add(query) # ran out of results for this query
                continue

            before = len(found)
            for item in items:
                # keyed by the unique id, NOT the model name: every colorway of a model shares one, so keying by name kept one colorway per model
                # skip anything without a current price, a $0 sneaker is no use in the shop (and not worth a detail lookup)
                # (prices come back as strings and "0" is truthy, so compare the number)
                if item.get("id") and item.get("product_type") == "sneakers" and float(item.get("lowest_ask") or 0) > 0:
                    found[item["id"]] = item
            print(f"🔍 {query} (page {page}): +{len(found) - before} ({len(found)} total)")

        if len(finished) == len(SEARCH_QUERIES):
            break

    return found


async def harvest_data():
    print("Fetching sneaker data 🚀")

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    sneaker_list = []
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        try:
            found = await search_sneakers(client)
            print(f"\nFound {len(found)} sneakers, fetching gender/description for each (~{len(found) * SECONDS_BETWEEN_REQUESTS / 60:.0f} min)...")

            # Phase 2: the search results are missing gender and description, the product endpoint has them
            for count, (shoe_id, search_item) in enumerate(found.items(), start=1):
                try:
                    details = await get_json(client, product_url, {"id": shoe_id, "market": "US"})
                except httpx.HTTPError as error:
                    print(f"couldn't get details for {search_item.get('title')}: {error}")
                    continue

                details = details.get("response", details) if isinstance(details, dict) else details
                details["lowest_ask"] = search_item.get("lowest_ask") # current price, only the search results have it
                details["link"] = search_item.get("link") or details.get("affiliate_url")
                sneaker_list.append(details)

                if count % 50 == 0:
                    print(f"   {count}/{len(found)} details fetched")
        except StopHarvest as reason:
            print(f"\nStopping early, the api refused the request ({reason})")

    print(f"\n{requests_made} requests made (~{requests_made * 0.4:.0f} credits)")

    # once we are done doing all the queries and everything we now have to get a proper list
    # and then dump everything as a json
    if not sneaker_list:
        sys.exit("No sneakers were harvested, keeping the existing sneakers.json") # never replace good data with an empty list

    with open(BACKEND_DIR / "sneakers.json", "w", encoding="utf-8") as file:
        json.dump(sneaker_list, file, indent=4)
    print(f"Successfully saved {len(sneaker_list)} sneakers to sneakers.json! ✅")

    if len(sneaker_list) < 500:
        print("⚠️ that's under 500, add more SEARCH_QUERIES and run it again")

if __name__ == "__main__":
    asyncio.run(harvest_data())
