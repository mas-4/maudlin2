from app.scrapers.voa import VOA
from app.scrapers.usatoday import USAToday
from app.scrapers.torontosun import TorontoSun
from app.scrapers.time import Time
from app.scrapers.week import Week
from app.scrapers.timesofindia import TimesofIndia
from app.scrapers.sun import Sun
from app.scrapers.intercept import Intercept
from app.scrapers.independent import Independent
from app.scrapers.hill import Hill
from app.scrapers.abc import ABC
from app.scrapers.aljazeera import AlJazeera
from app.scrapers.ap import AP
from app.scrapers.atlantic import Atlantic
from app.scrapers.bbc import BBC
from app.scrapers.blaze import Blaze
from app.scrapers.bloomberg import Bloomberg
from app.scrapers.breitbart import Breitbart
from app.scrapers.businessinsider import BusinessInsider
from app.scrapers.caixinglobal import CaixinGlobal
from app.scrapers.cbc import CBC
from app.scrapers.cbs import CBS
from app.scrapers.chicagotribune import ChicagoTribune
from app.scrapers.cnbc import CNBC
from app.scrapers.cnn import CNN
from app.scrapers.crooksandliars import CrooksandLiars
from app.scrapers.currentaffairs import CurrentAffairs
from app.scrapers.dailykos import DailyKos
from app.scrapers.dailymail import DailyMail
from app.scrapers.dailywire import DailyWire
from app.scrapers.derspiegel import DerSpiegel
from app.scrapers.drudgereport import DrudgeReport
from app.scrapers.economist import Economist
from app.scrapers.epochtimes import EpochTimes
from app.scrapers.federalist import Federalist
from app.scrapers.foreignaffairs import ForeignAffairs
from app.scrapers.foreignpolicy import ForeignPolicy
from app.scrapers.fortune import Fortune
from app.scrapers.fox import Fox
from app.scrapers.foxbusiness import FoxBusiness
from app.scrapers.ft import FT
from app.scrapers.globaltimes import GlobalTimes
from app.scrapers.globeandmail import GlobeAndMail
from app.scrapers.guardian import Guardian
from app.scrapers.huffpost import HuffPost
from app.scrapers.indiatimes import IndiaTimes
from app.scrapers.jacobin import Jacobin
from app.scrapers.kyivindependent import KyivIndependent
from app.scrapers.lemonde import LeMonde
from app.scrapers.military_com import MilitaryCom
from app.scrapers.moscowtimes import MoscowTimes
from app.scrapers.motherjones import MotherJones
from app.scrapers.nationalpost import NationalPost
from app.scrapers.nbc import NBC
from app.scrapers.newrepublic import NewRepublic
from app.scrapers.newyorker import NewYorker
from app.scrapers.newyorkmagazine import NewYorkMagazine
from app.scrapers.newyorkpost import NewYorkPost
from app.scrapers.nikkeiasia import NikkeiAsia
from app.scrapers.npr import NPR
from app.scrapers.nyt import NYT
from app.scrapers.pbsnewshour import PBSNewsHour
from app.scrapers.politicalwire import PoliticalWire
from app.scrapers.punchbowlnews import PunchbowlNews
from app.scrapers.quillette import Quillette
from app.scrapers.radiofreeeuroperadioliberty import RadioFreeEuropeRadioLiberty
from app.scrapers.rawstory import RawStory
from app.scrapers.reason import Reason
from app.scrapers.redstate import RedState
from app.scrapers.rt import RT
from app.scrapers.salon import Salon
from app.scrapers.scraper import SeleniumScraper
from app.scrapers.scrippsnews import ScrippsNews
from app.scrapers.semafor import Semafor
from app.scrapers.skynews import SkyNews
from app.scrapers.slate import Slate
from app.scrapers.southchinamorningpost import SouthChinaMorningPost
from app.scrapers.startribune import StarTribune
from app.scrapers.straitstimes import StraitsTimes
from app.scrapers.sydneymorningherald import SydneyMorningHerald
from app.scrapers.taipeitimes import TaipeiTimes
from app.scrapers.tampabaytimes import TampaBayTimes
from app.scrapers.telegraph import Telegraph

Scrapers = [
    VOA,
    USAToday,
    TorontoSun,
    Time,
    Week,
    TimesofIndia,
    Sun,
    Intercept,
    Independent,
    Hill,
    ABC,
    AP,
    AlJazeera,
    Atlantic,
    BBC,
    Blaze,
    Bloomberg,
    Breitbart,
    BusinessInsider,
    CBC,
    CBC,
    CBS,
    CNBC,
    CNN,
    CaixinGlobal,
    ChicagoTribune,
    CrooksandLiars,
    CurrentAffairs,
    DailyKos,
    DailyMail,
    DailyWire,
    DerSpiegel,
    DrudgeReport,
    Economist,
    EpochTimes,
    FT,
    Federalist,
    ForeignAffairs,
    ForeignPolicy,
    Fortune,
    Fox,
    FoxBusiness,
    GlobalTimes,
    GlobeAndMail,
    Guardian,
    HuffPost,
    IndiaTimes,
    Jacobin,
    KyivIndependent,
    LeMonde,
    MilitaryCom,
    MoscowTimes,
    MotherJones,
    NBC,
    NPR,
    NYT,
    NationalPost,
    NewRepublic,
    NewYorkMagazine,
    NewYorkPost,
    NewYorker,
    NikkeiAsia,
    PBSNewsHour,
    PoliticalWire,
    PunchbowlNews,
    Quillette,
    RT,
    RadioFreeEuropeRadioLiberty,
    RawStory,
    Reason,
    RedState,
    Salon,
    ScrippsNews,
    Semafor,
    SkyNews,
    Slate,
    SouthChinaMorningPost,
    StarTribune,
    StraitsTimes,
    SydneyMorningHerald,
    TaipeiTimes,
    TampaBayTimes,
    Telegraph,
]

TradScrapers = []
SeleniumScrapers = []

for scraper in Scrapers:
    if issubclass(scraper, SeleniumScraper):
        SeleniumScrapers.append(scraper)
    else:
        TradScrapers.append(scraper)
