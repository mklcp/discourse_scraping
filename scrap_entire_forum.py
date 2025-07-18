import os
import time
import json
from bs4 import BeautifulSoup
from collections import defaultdict
import requests
from urllib.parse import urljoin, urlparse
import sys
from io import BytesIO


HEADERS = {"User-Agent": "Googlebot (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}
REQUEST_DELAY = 0.5

def build_filepath(fs_path_array, url_path):
    return os.path.join(*fs_path_array, os.path.basename(url_path))

def build_url(base_url, url_path):
    return urljoin(base_url, url_path)

def print_indented(indent_level, msg, *args, **kwargs):
    print(f"{" "*indent_level}" + msg, *args, **kwargs)

def fetch(indent_level, full_url, json=True):
    try:
        resp = requests.get(full_url, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json() if json else resp.content
        time.sleep(REQUEST_DELAY)
        return data
    except Exception as e:
        print_indented(indent_level, f"[ERROR FETCHING] {full_url} : {e}")
        return None

def save(indent_level, filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        print(filepath)

def load_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def fetch_and_save(indent_level, base_url, url_path, fs_path_array):
    filepath = build_filepath(fs_path_array, url_path)
    full_url = build_url(base_url, url_path)
    if os.path.exists(filepath):
        print_indented(indent_level, f"[SKIPPED] Already downloaded: {full_url}")
        return load_json(filepath)
    data = fetch(indent_level, full_url, json=True)
    if data is not None:
        print_indented(indent_level, f"[FETCHED] {full_url} ", end="")
        save(indent_level, filepath, data)
    return data

def fetch_save_t(base_url, topics, fs_path_array):
    for topic in topics:
        topic_slug = topic.get("slug")
        topic_id = topic.get("id")
        if not topic_slug or not topic_id:
            continue
        fs_path_array[3] = topic_slug
        topic_url_path = f"/t/{topic_id}.json"
        topic_data = fetch_and_save(3, base_url, topic_url_path, fs_path_array[:4])

        fs_path_array[3] = ""

def extract_domain_name(base_url):
    domain_name = urlparse(base_url).netloc
    if not domain_name:
        print("[ERROR] cannot extract domain name")
        print("[HELP] Following the syntax specifications in RFC 1808, urlparse recognizes a netloc only if it is properly introduced by ‘//’. Otherwise the input is presumed to be a relative URL and thus to start with a path component.")
        return None
    return domain_name

def scrape_forum(base_url):
    domain_name = extract_domain_name(base_url)
    if domain_name is None:
        return None

    fs_path_array = [domain_name, "", "", ""] # domain, cat, subcat, topic
    cats_url_path = "/categories.json"

    categories = fetch_and_save(0, base_url, cats_url_path, fs_path_array[:1])

    for cat in categories.get("category_list", {}).get("categories", []):
        cat_slug = cat.get("slug")
        cat_id = cat.get("id")
        if not cat_slug or not cat_id:
            continue
        fs_path_array[1] = cat_slug
        cat_url_path = f"/c/{cat_id}.json"
        cat_data = fetch_and_save(1, base_url, cat_url_path, fs_path_array[:2])
        if not cat_data:
            continue

        subcats_url_path = cats_url_path + "?parent_category_id=" + str(cat_id)
        subcategories = fetch_and_save(1, base_url, subcats_url_path, fs_path_array[:2])

        topics_from_cat = cat_data.get("topic_list", {}).get("topics", [])
        topics_from_subcats = []

        for subcat in subcategories.get("category_list", {}).get("categories", []):
            subcat_slug = subcat.get("slug")
            subcat_id = subcat.get("id")
            if not subcat_slug or not subcat_id:
                continue
            fs_path_array[2] = subcat_slug
            cat_url_path = f"/c/{cat_id}/{subcat_id}.json"
            subcat_data = fetch_and_save(2, base_url, cat_url_path, fs_path_array[:3])
            if not subcat_data:
                continue

            topics = subcat_data.get("topic_list", {}).get("topics", [])
            topics_from_subcats.extend(topics)

            fetch_save_t(base_url, topics, fs_path_array)

            fs_path_array[2] = ""

        print_indented(1, f"[DIFF] {str(len(topics_from_subcats) == len(topics_from_cat))}, {len(topics_from_subcats)}, {len(topics_from_cat)}")
        if len(topics_from_subcats) != len(topics_from_cat):
            cat_ids = set(map(lambda x: x.get("id"), topics_from_cat))
            subcat_ids = set(map(lambda x: x.get("id"), topics_from_subcats))
            loner_ids = cat_ids - subcat_ids
            loner_topics = [t for t in topics_from_cat if t.get("id") in loner_ids]
            fs_path_array[2] = "_topics_without_a_subcategory"
            fetch_save_t(base_url, loner_topics, fs_path_array)

        fs_path_array[1] = ""

    fs_path_array[0] = ""


def find_all_pics(domain_name):
    highest_res_images = []

    # Recursively search for JSON files
    for root, _, files in os.walk(domain_name):
        for file in files:
            if file.endswith(".json"):
                json_path = os.path.join(root, file)
                
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    print(f"Skipping {json_path}: {e}")
                    continue

                posts = data.get("post_stream", {}).get("posts", [])
                
                for post in posts:
                    cooked = post.get("cooked", "")
                    soup = BeautifulSoup(cooked, "html.parser")

                    for img in soup.find_all("img"):
                        srcset_attr = img.get("srcset")
                        if not srcset_attr:
                            continue

                        scale_map = {}

                        # Parse the srcset
                        entries = [entry.strip() for entry in srcset_attr.split(",")]
                        for entry in entries:
                            parts = entry.rsplit(" ", 1)
                            if len(parts) == 2:
                                url, scale = parts
                                try:
                                    scale_factor = float(scale.replace("x", ""))
                                except ValueError:
                                    scale_factor = 1
                            else:
                                url = parts[0]
                                scale_factor = 1
                            scale_map[scale_factor] = url

                        # Get the highest resolution image
                        if scale_map:
                            max_scale = max(scale_map)
                            highest_res_url = scale_map[max_scale]
                            highest_res_images.append((highest_res_url, root))

    return highest_res_images

def save_img(content, url, full_path):
    with open(full_path, 'wb+') as destination:
        destination.write(content)
        print(f"[SAVED] {url} {full_path}")

def download_pics(base_url):
    domain_name = extract_domain_name(base_url)
    if domain_name is None:
        return None

    highest_res_images = find_all_pics(domain_name)
    print(f"[INFO] saving {len(highest_res_images)} pics.")
    for url, path in highest_res_images:
        resp = fetch(0, url, json=False)
        full_path = path + "/" + os.path.basename(url)
        save_img(resp, url, full_path)

BASE_URL = ""

if __name__ == "__main__":
    if len(sys.argv) == 3:
        BASE_URL = sys.argv[2]
        if sys.argv[1] == "json":
            scrape_forum(BASE_URL)
        elif sys.argv[1] == "pics":
            download_pics(BASE_URL)
        else:
            print(f"[ERROR] unknown subcommand: {sys.argv[1]}")
    else:
        print(f"[HELP] python {sys.argv[0]} [json|pics] $url")
