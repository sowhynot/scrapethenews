import random

from zenpy import Zenpy
import time
import requests
import configparser
import logging
import logging.config

from zenpy.lib.api_objects.help_centre_objects import Article
from retrying import retry


class Scraper:
    def __init__(self):

        logging.config.fileConfig('logging.ini')

        self.config = configparser.ConfigParser()
        self.config.read('config.ini')

        creds = {
            'email': self.config.get('zendesk', 'login'),
            'token': self.config.get('zendesk', 'token'),
            'subdomain': self.config.get('zendesk', 'subdomain')
        }

        self.pushoverparams = {
            'user': self.config.get('notifications', 'user'),
            'token': self.config.get('notifications', 'token'),
        }

        self.zenpy_client = Zenpy(**creds)

        with open('proxy.list') as f:
            self.proxy_list = f.read().splitlines()

    def create_dummy_article(self):
        return Article(title="Random Post",
                permission_group_id=self.config.get('zendesk','permissiongroupid'),
                user_segment_id=self.config.get('zendesk','usersegmentid'),
                locale="en-gb")

    # retrying, trying to use full list of proxies until none left
    def should_retry(self, result):
        if len(self.proxy_list) == 0:
            logging.error("No proxies available !")
            self.pushoverparams['message'] = 'Bot is down, no proxies available'
            requests.post('https://api.pushover.net/1/messages.json', params=self.pushoverparams)
            return False
        if result is None:
            logging.debug("{} proxies left".format(len(self.proxy_list)))
            return True
        else:
            return False

    def runscraper(self):

        @retry(retry_on_result=self.should_retry)
        def try_url(url):
            try:
                proxy_index = random.randint(0, len(self.proxy_list) - 1)
                proxy = {"http": self.proxy_list[proxy_index], "https": self.proxy_list[proxy_index]}
                logging.debug("Using proxy " + self.proxy_list[proxy_index])
                r = requests.get(url, proxies=proxy, timeout=(2, 2))
                logging.debug(r.status_code)
                return r
            except Exception as e:
                logging.error(e)
                logging.error("Proxy " + self.proxy_list[proxy_index] + " down")
                self.proxy_list.remove(self.proxy_list[proxy_index])

        previousid = 0
        seq1previousid = self.zenpy_client.help_center.articles.create(section=self.config.get('zendesk', 'section'),article=self.create_dummy_article()).id

        # There seems to be two distinct sequences, if difference between two new article ids is large, means the id was assigned from the other sequence
        # trying to grab other sequence
        while True:
            id = self.zenpy_client.help_center.articles.create(section=self.config.get('zendesk', 'section'),article=self.create_dummy_article())
            if abs(id.id - seq1previousid) > 1000: #large id difference means we got an id from the other sequence
                seq2previousid = id.id
                previousid = id.id
                break

        while True:

            currentid = self.zenpy_client.help_center.articles.create(section=self.config.get('zendesk', 'section'),article=self.create_dummy_article()).id

            if abs(currentid - previousid) > 1000:
                nbarticlestotest = currentid - seq1previousid
                rangestart = seq1previousid
                seq1previousid = currentid
            else:
                nbarticlestotest = currentid - seq2previousid
                rangestart = seq2previousid
                seq2previousid = currentid


            logging.debug(nbarticlestotest)
            logging.debug(rangestart)
            logging.debug(rangestart + nbarticlestotest)

            for i in range(rangestart, rangestart + nbarticlestotest, 1):
                url = 'https://www.binance.com/en/support/articles/{}'.format(i)
                logging.info("Testing {}".format(url))
                r = None
                if not self.config.getboolean('general', 'testmode'):
                    r = try_url(url)
                if r is not None and r.status_code == 200:
                    logging.info("Found news !")
                    self.pushoverparams['message'] = 'New Binance news ! {}'.format(url)
                    requests.post('https://api.pushover.net/1/messages.json', params=self.pushoverparams)
                if r is not None and r.status_code == 429:
                    self.pushoverparams['message'] = 'Bot is being throttled, going down!'.format(url)
                    requests.post('https://api.pushover.net/1/messages.json', params=self.pushoverparams)
                    exit(-1)
                time.sleep(0.1)
