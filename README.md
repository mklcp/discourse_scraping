# discourse_scraping

A simple Discourse scraper.

The quality of the code and the ease of use is proportional to the usage I made of it, that is almost never.

Just putting this code here if it ever helps somebody.

PRs welcome. But don't expect me to respond fast.

## Usage
Two passes model:

```
python scrap_entire_forum.py json $url
python scrap_entire_forum.py pics $url
```

So that if you ever get rate-limited or worse, you have at least the forum structure
