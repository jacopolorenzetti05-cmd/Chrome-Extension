# Chrome-Extension
Building an Extension for programming class

## Book scraper + database experiment

Scrapes **books.toscrape.com** into a linked SQLite database
(`categories`, `ratings`, `books`, `scrape_runs`, `book_snapshots`).
Design, schema diagram and data flow: [`book_scraper/DESIGN.md`](book_scraper/DESIGN.md).

```bash
pip install -r requirements.txt

python -m unittest discover -s tests     # offline tests (HTML fixtures)
python -m book_scraper sample            # step 2: scrape one book, print the record
python -m book_scraper smoke             # step 3: write one row, read it back
python -m book_scraper check             # step 4: test site + database connection
python -m book_scraper run --max-pages 2 # step 5: scrape 2 pages (omit for all 50)
sqlite3 books.db "SELECT * FROM v_books LIMIT 5"
```
