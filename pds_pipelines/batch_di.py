#!/usr/bin/env python

import datetime
import json
import logging
import argparse
import pytz
from pds_pipelines.find_di_ready import archive_expired
from pds_pipelines.redis_queue import RedisQueue
from pds_pipelines.db import db_connect
from pds_pipelines.config import pds_info, pds_db, pds_log


def parse_args():
    parser = argparse.ArgumentParser(description="DI Process")

    parser.add_argument('--log', '-l', dest="log_level",
                        choices=['DEBUG', 'INFO',
                                'WARNING', 'ERROR', 'CRITICAL'],
                        help="Set the log level.", default='INFO')

    args = parser.parse_args()
    return args


def main(user_args):
    log_level = user_args.log_level

    logger = logging.getLogger('DI_Queueing')
    level = logging.getLevelName(log_level)
    logger.setLevel(level)
    logFileHandle = logging.FileHandler(pds_log + 'DI.log')
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s, %(message)s')
    logFileHandle.setFormatter(formatter)
    logger.addHandler(logFileHandle)

    PDS_info = json.load(open(pds_info, 'r'))
    reddis_queue = RedisQueue('DI_ReadyQueue')

    logger.info("DI Queue: %s", reddis_queue.id_name)

    try:
        Session, _ = db_connect(pds_db)
        session = Session()
    except Exception as e:
        logger.error("%s", e)
        return 1

    for target in PDS_info:
        archive_id = PDS_info[target]['archiveid']
        td = (datetime.datetime.now(pytz.utc)
              - datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        testing_date = datetime.datetime.strptime(str(td), "%Y-%m-%d %H:%M:%S")
        expired = archive_expired(session, archive_id, testing_date)
        # If any files within the archive are expired, send them to the queue
        if expired.count():
            for f in expired:
                reddis_queue.QueueAdd((f.filename, target))
            logger.info('Archive %s DI Ready: %s Files', target, str(expired.count()))
        else:
            logger.info('Archive %s DI Current', target)
    return 0


if __name__ == "__main__":
    main(parse_args())
