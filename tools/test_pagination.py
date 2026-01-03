
import requests
from bs4 import BeautifulSoup

INVESTITION_URL = "https://ronson.pl/inwestycja/grunwald-miedzy-drzewami/"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

def get_count(offset):
    url = f"{INVESTITION_URL}?ajax_part=1&offset_more={offset}"
    print(f"Fetching offset {offset}...")
    r = requests.get(url, headers={"User-Agent": UA})
    soup = BeautifulSoup(r.text, "lxml")
    cards = soup.select(".item-apartment:not(.item-apartment--see-more)")
    print(f"Offset {offset}: found {len(cards)} cards")
    return len(cards)

get_count(7)
get_count(14)
get_count(100)
