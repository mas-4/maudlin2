from app.scraper import SeleniumScraper
from app.scrapers.abc import ABC
from app.scrapers.aljazeera import AlJazeera
from app.scrapers.alternet import Alternet
from app.scrapers.ap import AP
from app.scrapers.atlantic import Atlantic
from app.scrapers.axios import Axios
from app.scrapers.bbc import BBC
from app.scrapers.blaze import Blaze
from app.scrapers.bloomberg import Bloomberg
from app.scrapers.breitbart import Breitbart
from app.scrapers.bulwark import Bulwark
from app.scrapers.businessinsider import BusinessInsider
from app.scrapers.caixinglobal import CaixinGlobal
from app.scrapers.cbc import CBC
from app.scrapers.cbs import CBS
from app.scrapers.chicagotribune import ChicagoTribune
from app.scrapers.christiansciencemonitor import ChristianScienceMonitor
from app.scrapers.cnbc import CNBC
from app.scrapers.cnn import CNN
from app.scrapers.crooksandliars import CrooksandLiars
from app.scrapers.currentaffairs import CurrentAffairs
from app.scrapers.dailybeast import DailyBeast
from app.scrapers.dailycaller import DailyCaller
from app.scrapers.dailykos import DailyKos
from app.scrapers.dailymail import DailyMail
from app.scrapers.dailywire import DailyWire
from app.scrapers.derspiegel import DerSpiegel
from app.scrapers.dispatch import Dispatch
from app.scrapers.drudgereport import DrudgeReport
from app.scrapers.economist import Economist
from app.scrapers.epochtimes import EpochTimes
from app.scrapers.federalist import Federalist
from app.scrapers.forbes import Forbes
from app.scrapers.foreignaffairs import ForeignAffairs
from app.scrapers.foreignpolicy import ForeignPolicy
from app.scrapers.fortune import Fortune
from app.scrapers.fox import Fox
from app.scrapers.foxbusiness import FoxBusiness
from app.scrapers.france24 import France24
from app.scrapers.ft import FT
from app.scrapers.gatewaypundit import GatewayPundit
from app.scrapers.globaltimes import GlobalTimes
from app.scrapers.globeandmail import GlobeAndMail
from app.scrapers.googlenews import GoogleNews
from app.scrapers.guardian import Guardian
from app.scrapers.hill import Hill
from app.scrapers.huffpost import HuffPost
from app.scrapers.independent import Independent
from app.scrapers.independentjournalreview import IndependentJournalReview
from app.scrapers.indianexpress import IndianExpress
from app.scrapers.indiatimes import IndiaTimes
from app.scrapers.intercept import Intercept
from app.scrapers.jacobin import Jacobin
from app.scrapers.japantimes import JapanTimes
from app.scrapers.kyivindependent import KyivIndependent
from app.scrapers.lemonde import LeMonde
from app.scrapers.losangelestimes import LosAngelesTimes
from app.scrapers.marketwatch import MarketWatch
from app.scrapers.military_com import MilitaryCom
from app.scrapers.mint import Mint
from app.scrapers.moscowtimes import MoscowTimes
from app.scrapers.motherjones import MotherJones
from app.scrapers.msnbc import MSNBC
from app.scrapers.nation import Nation
from app.scrapers.nationalpost import NationalPost
from app.scrapers.nationalreview import NationalReview
from app.scrapers.nbc import NBC
from app.scrapers.ndtv import NDTV
from app.scrapers.newrepublic import NewRepublic
from app.scrapers.news18 import News18
from app.scrapers.newsmax import Newsmax
from app.scrapers.newsnation import NewsNation
from app.scrapers.newsweek import Newsweek
from app.scrapers.newyorker import NewYorker
from app.scrapers.newyorkmagazine import NewYorkMagazine
from app.scrapers.newyorkpost import NewYorkPost
from app.scrapers.nikkeiasia import NikkeiAsia
from app.scrapers.npr import NPR
from app.scrapers.nyt import NYT
from app.scrapers.oann import OneAmericaNewsNetwork
from app.scrapers.pbsnewshour import PBSNewsHour
from app.scrapers.politicalwire import PoliticalWire
from app.scrapers.politico import Politico
from app.scrapers.postmillennial import PostMillennial
from app.scrapers.propublica import ProPublica
from app.scrapers.punchbowlnews import PunchbowlNews
from app.scrapers.quillette import Quillette
from app.scrapers.radiofreeeuroperadioliberty import RadioFreeEuropeRadioLiberty
from app.scrapers.rawstory import RawStory
from app.scrapers.realclearpolitics import RealClearPolitics
from app.scrapers.reason import Reason
from app.scrapers.redstate import RedState
from app.scrapers.reuters import Reuters
from app.scrapers.rollingstone import RollingStone
from app.scrapers.rt import RT
from app.scrapers.salon import Salon
from app.scrapers.scrippsnews import ScrippsNews
from app.scrapers.semafor import Semafor
from app.scrapers.skynews import SkyNews
from app.scrapers.slate import Slate
from app.scrapers.southchinamorningpost import SouthChinaMorningPost
from app.scrapers.startribune import StarTribune
from app.scrapers.sun import Sun
from app.scrapers.sydneymorningherald import SydneyMorningHerald
from app.scrapers.taipeitimes import TaipeiTimes
from app.scrapers.tampabaytimes import TampaBayTimes
from app.scrapers.telegraph import Telegraph
from app.scrapers.time import Time
from app.scrapers.timesofindia import TimesofIndia
from app.scrapers.torontosun import TorontoSun
from app.scrapers.townhall import Townhall
from app.scrapers.usatoday import USAToday
from app.scrapers.vanityfair import VanityFair
from app.scrapers.voa import VOA
from app.scrapers.vox import Vox
from app.scrapers.wallstreetjournal import WallStreetJournal
from app.scrapers.washingtonexaminer import WashingtonExaminer
from app.scrapers.washingtonfreebeacon import WashingtonFreeBeacon
from app.scrapers.washingtonpost import WashingtonPost
from app.scrapers.washingtontimes import WashingtonTimes
from app.scrapers.week import Week
from app.scrapers.winnipegfreepress import WinnipegFreePress
from app.scrapers.xinhua import Xinhua
from app.scrapers.yahoonews import YahooNews

Scrapers = [
    # HindustanTimes,
    # InfoWars,
    # NationalInterest,
    # StraitsTimes,
    ABC,
    AP,
    AlJazeera,
    Alternet,
    Atlantic,
    Axios,
    BBC,
    Blaze,
    Bloomberg,
    Breitbart,
    Bulwark,
    BusinessInsider,
    CBC,
    CBS,
    CNBC,
    CNN,
    CaixinGlobal,
    ChicagoTribune,
    ChristianScienceMonitor,
    CrooksandLiars,
    CurrentAffairs,
    DailyBeast,
    DailyCaller,
    DailyKos,
    DailyMail,
    DailyWire,
    DerSpiegel,
    Dispatch,
    DrudgeReport,
    Economist,
    EpochTimes,
    FT,
    Federalist,
    Forbes,
    ForeignAffairs,
    ForeignPolicy,
    Fortune,
    Fox,
    FoxBusiness,
    France24,
    GatewayPundit,
    GlobalTimes,
    GlobeAndMail,
    GoogleNews,
    Guardian,
    Hill,
    HuffPost,
    Independent,
    IndependentJournalReview,
    IndiaTimes,
    Intercept,
    Jacobin,
    JapanTimes,
    KyivIndependent,
    LeMonde,
    LosAngelesTimes,
    MSNBC,
    MarketWatch,
    MilitaryCom,
    Mint,
    MoscowTimes,
    MotherJones,
    NBC,
    NDTV,
    NPR,
    NYT,
    Nation,
    NationalPost,
    NationalReview,
    NewRepublic,
    NewYorkMagazine,
    NewYorkPost,
    NewYorker,
    News18,
    NewsNation,
    Newsmax,
    Newsweek,
    NikkeiAsia,
    OneAmericaNewsNetwork,
    PBSNewsHour,
    PoliticalWire,
    Politico,
    PostMillennial,
    ProPublica,
    PunchbowlNews,
    Quillette,
    RT,
    RadioFreeEuropeRadioLiberty,
    RawStory,
    RealClearPolitics,
    Reason,
    RedState,
    Reuters,
    RollingStone,
    Salon,
    ScrippsNews,
    Semafor,
    SkyNews,
    Slate,
    SouthChinaMorningPost,
    StarTribune,
    Sun,
    SydneyMorningHerald,
    TaipeiTimes,
    TampaBayTimes,
    Telegraph,
    Time,
    TimesofIndia,
    TorontoSun,
    Townhall,
    USAToday,
    VOA,
    VanityFair,
    Vox,
    WallStreetJournal,
    WashingtonExaminer,
    WashingtonFreeBeacon,
    WashingtonPost,
    WashingtonTimes,
    Week,
    WinnipegFreePress,
    Xinhua,
    YahooNews,
]

TradScrapers = []
SeleniumScrapers = []

for scraper in Scrapers:
    if issubclass(scraper, SeleniumScraper):
        SeleniumScrapers.append(scraper)
    else:
        TradScrapers.append(scraper)

ScraperDict = {scraper.agency: scraper for scraper in Scrapers}
