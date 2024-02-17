from app.scrapers.thetelegraph import TheTelegraph
from app.scrapers.tampabaytimes import TampaBayTimes
from app.scrapers.sydneymorningherald import SydneyMorningHerald
from app.scrapers.startribune import StarTribune
from app.scrapers.southchinamorningpost import SouthChinaMorningPost
from app.scrapers.slate import Slate
from app.scrapers.skynews import SkyNews
from app.scrapers.scrippsnews import ScrippsNews
from app.scrapers.punchbowlnews import PunchbowlNews
from app.scrapers.redstate import RedState
from app.scrapers.reason import Reason
from app.scrapers.radiofreeeuroperadioliberty import RadioFreeEuropeRadioLiberty
from app.scrapers.politicalwire import PoliticalWire
from app.scrapers.nationalpost import NationalPost
from app.scrapers.themoscowtimes import TheMoscowTimes
from app.scrapers.military_com import MilitaryCom
from app.scrapers.scraper import SeleniumScraper
from app.scrapers.crooksandliars import CrooksandLiars
from app.scrapers.cbc import CBC
from app.scrapers.taipeitimes import TaipeiTimes
from app.scrapers.thekyivindependent import TheKyivIndependent
from app.scrapers.thestraitstimes import TheStraitsTimes
from app.scrapers.abc import ABC
from app.scrapers.aljazeera import AlJazeera
from app.scrapers.ap import AP
from app.scrapers.bbc import BBC
from app.scrapers.bloomberg import Bloomberg
from app.scrapers.breitbart import Breitbart
from app.scrapers.businessinsider import BusinessInsider
from app.scrapers.caixinglobal import CaixinGlobal
from app.scrapers.cbs import CBS
from app.scrapers.chicagotribune import ChicagoTribune
from app.scrapers.cnbc import CNBC
from app.scrapers.cnn import CNN
from app.scrapers.currentaffairs import CurrentAffairs
from app.scrapers.dailykos import DailyKos
from app.scrapers.dailymail import DailyMail
from app.scrapers.derspiegel import DerSpiegel
from app.scrapers.drudgereport import DrudgeReport
from app.scrapers.economist import Economist
from app.scrapers.foreignaffairs import ForeignAffairs
from app.scrapers.foreignpolicy import ForeignPolicy
from app.scrapers.fortune import Fortune
from app.scrapers.fox import Fox
from app.scrapers.foxbusiness import FoxBusiness
from app.scrapers.ft import FT
from app.scrapers.globaltimes import GlobalTimes
from app.scrapers.huffpost import HuffPost
from app.scrapers.indiatimes import IndiaTimes
from app.scrapers.jacobin import Jacobin
from app.scrapers.lemonde import LeMonde
from app.scrapers.motherjones import MotherJones
from app.scrapers.nbc import NBC
from app.scrapers.newrepublic import NewRepublic
from app.scrapers.newyorker import NewYorker
from app.scrapers.newyorkmagazine import NewYorkMagazine
from app.scrapers.newyorkpost import NewYorkPost
from app.scrapers.nikkeiasia import NikkeiAsia
from app.scrapers.npr import NPR
from app.scrapers.nyt import NYT
from app.scrapers.pbsnewshour import PBSNewsHour
from app.scrapers.quillette import Quillette
from app.scrapers.rawstory import RawStory
from app.scrapers.rt import RT
from app.scrapers.salon import Salon
from app.scrapers.semafor import Semafor

Scrapers = [
    TheTelegraph,
    TampaBayTimes,
    SydneyMorningHerald,
    StarTribune,
    SouthChinaMorningPost,
    Slate,
    SkyNews,
    ScrippsNews,
    PunchbowlNews,
    RedState,
    Reason,
    RadioFreeEuropeRadioLiberty,
    PoliticalWire,
    NationalPost,
    TheMoscowTimes,
    ABC,
    AP,
    AlJazeera,
    BBC,
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
    DerSpiegel,
    DrudgeReport,
    Economist,
    FT,
    ForeignAffairs,
    ForeignPolicy,
    Fortune,
    Fox,
    FoxBusiness,
    GlobalTimes,
    HuffPost,
    IndiaTimes,
    Jacobin,
    LeMonde,
    MilitaryCom,
    MotherJones,
    NBC,
    NPR,
    NYT,
    NewRepublic,
    NewYorkMagazine,
    NewYorkPost,
    NewYorker,
    NikkeiAsia,
    PBSNewsHour,
    Quillette,
    RT,
    RawStory,
    Salon,
    Semafor,
    TaipeiTimes,
    TheKyivIndependent,
    TheStraitsTimes,
]

TradScrapers = []
SeleniumScrapers = []

for scraper in Scrapers:
    if issubclass(scraper, SeleniumScraper):
        SeleniumScrapers.append(scraper)
    else:
        TradScrapers.append(scraper)
