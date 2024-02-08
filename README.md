# maudlin

Maudlin is a news aggregator and sentiment analyzer. It scrapes the front page of most news sites and analyzes the
sentiment in each story.

The current app is available at http://maudlin.standingwater.io

## Basic Premise

The idea I'm working with is a successor to the first Maudlin (now defunct) that can be found here: https://github.com/mas-4/maudlin. Its problems were manifold, chief among them that it was a web app! It generated pages on access instead of just generating a static site, which this new version does. It also used Flask and Scrapy and this new one is 90% rolled by me. (tech stack below)

Right now my focus is not on compiling a huge database of articles (I keep deleting the database as I add features for now) but rather on getting a basic idea of the sentiment of the front page of news sources. Toward that end, in order to stay (more) legal than my previous version was, I'm going to skip trying to dodge paywalls and anti-bot measures (recently discovered just mimicking the GoogleBot's User Agent will open a lot of paywalls!) and instead just focus on headlines. I now have a headline sentiment and an article sentiment. Article sentiment will exclude sources like NYT. Headlines also change through the day! So I am going to try to work on figuring out how to update headlines. Instead of using url's for uniqueness I may start using titles.

I also am using www.mediabiasfactcheck.com to get a partisan score and a factuality score which will allow me to do some more interesting metrics. And I'm trying my best to remove useless words.

## Tech Stack

I'm using requests and BeautifulSoup to do all my scraping. I built my own spider framework basically and I think its shockingly clean! It runs all the spiders at once in a multithreaded environment. The scrape and build is kicked off at the top of the hour every hour.

The data is stored in an sqlite database using SQLAlchemy 2.0+ as an ORM.

I use nltk, punkt, vader_lexicon, and averaged_perceptron_tagger for all my sentiment analysis.

[wordcloud](https://pypi.org/project/wordcloud/) to make the wordclouds.

And jinja2 is used for templating.

There's some pandas and numpy in there for something but I can't remember what. I expect more use of those later on.

## Testing

Not really sure how to do testing. I guess the site builder could be tested but meh. I'm a pretty TDD guy but kinda hard to test scrapers. I had a test suite and have abandoned it. Sites change, scrapers have to be updated. I'd rather add in some features to get a good sense of what's going wrong so eventually I'm going to add an email system to just send me a daily update of what's failing to get parsed.

## Sites to add

If you know of a good source not on this list please open an issue!

- [ ] ABC News
- [ ] Al Jazeera
- [X] Associated Press
- [-] Axios
- [ ] BBC
- [ ] Barron's
- [X] Breitbart
- [ ] Business Insider
- [X] CBS News
- [X] CNBC
- [ ] Daily Beast
- [ ] Daily Kos
- [ ] Daily mail
- [ ] FT
- [ ] Forbes
- [ ] Foreign Affairs
- [ ] Foreign Policy
- [ ] Fortune
- [ ] Fox Business
- [ ] Global Times
- [ ] Huffington Post
- [ ] India Times
- [ ] Jacobin
- [ ] MSNBC
- [ ] Mother Jones
- [ ] New York Post
- [ ] New Yorker
- [ ] Newsweek
- [ ] PBS News Hour
- [ ] Politico
- [ ] Reuters
- [ ] Salon
- [X] Semafor
- [ ] Slate
- [ ] South China Morning Post
- [ ] Tampa Bay Times
- [ ] Telegraph
- [ ] The Atlantic?
- [ ] The Blaze
- [ ] The Daily Wire
- [ ] The Guardian
- [ ] The Hill
- [ ] The Independent
- [ ] The Intercept
- [ ] Time
- [ ] USA Today
- [ ] VOA
- [ ] Vanity Fair
- [ ] Vice
- [ ] Vox
- [ ] WSJ
- [ ] Wapo
- [ ] Xinhua
- [X] CNN
- [X] NBC
- [X] NPR
- [X] The New York Times (Disabled for legality)
- [x] Fox News