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

## Testing

Not really sure how to do testing. I guess the site builder could be tested but meh. I'm a pretty TDD guy but kinda hard to test scrapers. I had a test suite and have abandoned it. Sites change, scrapers have to be updated. I'd rather add in some features to get a good sense of what's going wrong. I have a daily report system that gets emailed to me every morning and I keep extensive logs and daily backups. Over the weekend (end of March) my entire machine went down so I missed a day of articles. But that's what happens when you run this thing out of your garage.

## Sites to add

If you know of a good source not on this list please open an issue or a PR! Feel free to make new scrapers!

- [X] The Daily Caller
- [X] Gateway Pundit
- [X] Washington Free Beacon
- [X] The Washington Times
- [X] Townhall
- [X] Washington Examiner
- [X] Independent Journal Review
- [X] alternet
- [x] One America News
- [x] Newsmax
- [X] ABC News
- [X] Al Jazeera
- [X] Associated Press
- [X] Axios
- [X] BBC
- [X] Barron
- [X] Bloomberg
- [X] Breitbart
- [X] Business Insider
- [X] CBC
- [X] CBS News
- [X] CNBC
- [X] CNN
- [X] Caixin Global
- [X] Chicago Tribune
- [X] Crooks and Liars
- [X] Current Affairs
- [X] Daily Beast
- [X] Daily Kos
- [X] Daily mail
- [X] Der Spiegel
- [X] Economist
- [X] FT
- [X] Forbes
- [X] Foreign Affairs
- [X] Foreign Policy
- [X] Fortune
- [X] Fox Business
- [X] Fox News
- [X] France 24
- [X] Global Times
- [X] Google News
- [X] Hindustan Times (Chromium)
- [X] Huffington Post
- [X] India Times
- [X] Infowars (403)
- [X] Jacobin
- [X] Japan Times
- [X] Kyiv Independent
- [X] LA Times
- [X] Le Monde
- [X] MSNBC (requires more sophisticated filtering)
- [X] Military.com
- [X] Moscow Times
- [X] Mother Jones
- [X] NBC
- [X] NPR
- [X] National Interest
- [X] National Post
- [X] National Review (javascript only)
- [X] New Republic
- [X] New York Magazine
- [X] New York Post
- [X] New Yorker
- [X] Newsweek (403)
- [X] Nikkei Asia
- [X] PBS News Hour
- [X] Political Wire
- [X] Politico (javascript)
- [X] Punchbowl
- [X] Quillette
- [X] RT
- [X] Radio Free Europe
- [X] Raw Story
- [X] Real Clear Politics (Assholes)
- [X] Reason
- [X] Red State
- [X] Reuters (401?)
- [X] Rolling Stone
- [X] Salon
- [X] Scripps
- [X] Semafor
- [X] Sky News
- [X] Slate
- [X] South China Morning Post
- [X] Star Tribune
- [X] Strait Times
- [X] Sydney Morning Herald
- [X] Taipei Times
- [X] Tampa Bay Times
- [X] Telegraph
- [X] The Atlantic
- [X] The Blaze
- [X] The Daily Wire
- [X] The Epoch Times
- [X] The Federalist
- [X] The Globe and Mail
- [X] The Guardian
- [X] The Hill
- [X] The Independent
- [X] The Intercept
- [X] The New York Times
- [X] The Sun
- [X] The Times of India
- [X] The Week
- [X] Time
- [X] Toronto Sun
- [X] USA Today
- [X] VOA
- [X] Vanity Fair
- [X] Vice
- [X] Vox
- [X] Wall Street Journal (401/403)
- [X] Washington Post
- [X] Winnipeg Free Press
- [X] Xinhua
- [X] indianexpress.com
- [X] livemint.com
- [X] ndtv.com
- [X] news.yahoo.com
- [X] news18.com
