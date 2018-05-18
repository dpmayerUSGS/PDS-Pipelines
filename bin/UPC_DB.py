#!/usgs/apps/anaconda/bin/python

from sqlalchemy import *
from sqlalchemy.orm.util import *

from db import db_connect
from PDS_DBsessions import *
from config import *

from models import upc_models

class UPC_DB(object):

    def __init__(self):
        self.session, _ = db_connect('upcdev')
        self.datafiles = upc_models.DataFiles
        self.targets = upc_models.Targets

    def testIsisId(self, isisid):

        qOBJ = self.session.query(self.datafiles).filter(
            self.datafiles.isisid == isisid).first()
        return qOBJ.isisid

    def getUPCid(self, isisid):

        qOBJ = self.session.query(self.datafiles).filter(
            self.datafiles.isisid == isisid).first()
        return qOBJ.upcid

    def getTargetID(self, target):

        qOBJ = self.session.query(self.targets).filter(
            self.targets.targetname == upper(target)).first()
        return queryObj.targetid
