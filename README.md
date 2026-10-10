# maudlin

Maudlin is a news aggregator, sentiment analyzer, and topic tracker (so far!). It scrapes the front page of most news sites and analyzes the headlines for insights about events and the election and the way the news is talking about them.

The current app is available at https://maudlin.news.

## Basic Premise

The idea I'm working with is a successor to the first Maudlin (now defunct) that can be found here: https://github.com/mas-4/maudlin. Its problems were manifold, chief among them that it was a web app! It generated pages on access instead of just generating a static site, which this new version does. It also used Flask and Scrapy and this new one is 90% rolled by me. (tech stack below)

The biggest change from the earlier version besides the flask system is now we don't scrape articles. We're headlines only. This limits the difficulty in maintaining 114 different scrapers. It also limits the amount of data I need to store.

I am using www.mediabiasfactcheck.com to get a partisan score and a factuality score which will allow me to do some more interesting metrics. And I'm trying my best to remove useless words.

## Tech Stack

I'm using requests, selenium with headless Firefox, and BeautifulSoup to do all my scraping. I built my own spider framework basically and I think its shockingly clean! It runs all the spiders at once in a multithreaded environment. The scrape and build is kicked off every half hour last time I updated this README.

The data is stored in an sqlite database using SQLAlchemy 2.0+ as an ORM.

I use nltk, punkt, vader_lexicon, AFINN, and averaged_perceptron_tagger for all my sentiment analysis.

I've started analyzing articles for handcrafted topics, focusing on topics relevant to the election, like Biden is Old or Trump Trials. This topic analysis does not use LDA or K-Means or any off the shelf algorithm, it relies on bags of words and similarity scores.

[wordcloud](https://pypi.org/project/wordcloud/) to make the wordclouds.

And jinja2 is used for templating.

There's a lot of pandas and numpy in there at this point. Some gensim I think. And textacy/spacy. Matplotlib and Seaborn of course. gridJS for tables. ChatGPT Plus came up with css styling and general debugging.

I've experimented with a lot of different models for toppic modeling and story discovery. Finally got story discovery working by using an agglomerative approach with cosine_similarity (sklearn) and strict cluster requirements (at least n number of samples from different news agencies with cosine similarity scores over 0.5).

I plan on adding some more sophisticated sentiment scoring, and using hugging face models for text preprocessing and summarization.

I've actually read the better part of two books in the course of making this thing, [Blueprints for Text Analytics Using Python: Machine Learning-Based Solutions for Common Real World (NLP) Applications](https://www.amazon.com/gp/product/149207408X/ref=ppx_yo_dt_b_search_asin_title?ie=UTF8&psc=1) and [The Handbook of NLP with Gensim: Leverage topic modeling to uncover hidden patterns, themes, and valuable insights within textual data
](https://www.amazon.com/gp/product/1803244941/ref=ppx_yo_dt_b_search_asin_title?ie=UTF8&psc=1)

Oh! And the site is hosted on netlify. It's just a bunch of flat files I upload to netlify.

## 2026 Setup

- `pip install -r requirements.txt`, `python setup.py build_ext --inplace` for the C clustering extension, then
  `alembic upgrade head`.
- Most outlets are read from their RSS feeds (`FeedScraper`); custom HTML scrapers remain for outlets without one.
- Story clustering uses [model2vec](https://github.com/MinishLab/model2vec) sentence embeddings, downloaded from
  Hugging Face on first use (~30MB).
- Optional LLM features run on a small open model served locally by [Ollama](https://ollama.com) (default
  `qwen3:8b`, which fits a 10GB GPU). Set `MAUDLIN_LLM_MODEL` to use another model, or `MAUDLIN_LLM=anthropic`
  with a key in `.anthropic_creds` to use Claude instead. With no LLM available these features are skipped and the
  site builds as before.
  - Neutral story titles are written once per new story.
  - Each new headline gets one LLM call that returns three judgments: whether it's news (non-news stays out of the
    analyses), how good or bad the event is for the people it affects (-2 to 2), and how loaded the outlet's own
    wording is (0 to 2). These replace VADER/AFINN in the mood meters and framing charts; the old scores are kept,
    and used when no LLM is running. `--rescore-news` rejudges everything stored after a rubric change. For when no
    LLM is running, `--label-headlines 3000` then `--train-newsfilter` builds a small fallback news classifier.
- Each scrape also records Bluesky's trending topics and refreshes polling data: Senate race averages computed
  from [VoteHub](https://votehub.com/polls/) polls (CC BY 4.0), and the published national averages as tabulated on
  Wikipedia (CC BY-SA 4.0).
- `--debug` builds from the newest data in the database instead of the last ten minutes.

## Testing

Not really sure how to do testing. I guess the site builder could be tested but meh. I'm a pretty TDD guy but kinda hard to test scrapers. I had a test suite and have abandoned it. Sites change, scrapers have to be updated. I'd rather add in some features to get a good sense of what's going wrong. I have a daily report system that gets emailed to me every morning and I keep extensive logs and daily backups. Over the weekend (end of March) my entire machine went down so I missed a day of articles. But that's what happens when you run this thing out of your garage.

## License

Copyright (c) 2024-2026 Michael.

- **Code:** GNU Affero General Public License v3 or later ([LICENSE](LICENSE)). Run a modified copy as a service
  and you share your changes under the same license. Versions published before October 8, 2026 were MIT, and copies
  of those stay MIT; the code was proprietary from October 8 to 10.
- **Docs** (`docs/`: the methods log, the motif praxis and casebook, the experiment write-ups): CC BY 4.0, with
  credit to bignews.day.
- **The motif index** (on bignews.day and in its exports, not in this repository): CC BY-NC-SA 4.0, with credit to
  bignews.day; commercial use needs permission.
- **Third-party data** keeps its own license: `ratings.csv` carries AllSides Media Bias Ratings (CC BY-NC 4.0) and
  Wikipedia's perennial sources list (CC BY-SA 4.0); `outlet_wiki.csv` quotes Wikipedia (CC BY-SA 4.0).
- **Contributions:** not accepted for now.
