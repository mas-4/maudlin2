from app import j2env
from app.models import Session, Agency
from app.config import Config
import os

def generate_agency_pages():
    template = j2env.get_template('agency.html')
    with Session() as s:
        for agency in s.query(Agency).all():
            with open(os.path.join(Config.build, f'{agency.name}.html'), 'wt') as f:
                f.write(template.render(title=agency.name, agency=agency))

def build_site():
    generate_agency_pages()

