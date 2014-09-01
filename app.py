from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash, _app_ctx_stack

import requests
from bs4 import BeautifulSoup
import time
from time import mktime
from datetime import datetime
import re
# import logging
import json
import mandrill
# from pprint import pprint

# Packages installed
# requests
# BeautifulSoup4
# Mandrill

# configuration
DEBUG = True
# HOST = '0.0.0.0'
LOGFILE_NAME = "hansardhack.log"

# to-do
# Handle situations like DailyTranscripts 404 by throwing exceptions and notifying us somehow

# create our little application
app = Flask(__name__)
app.config.from_object(__name__)
app.config.from_envvar('FLASKR_SETTINGS', silent=True)

# logging setup
# logging.basicConfig(filename=LOGFILE_NAME,format='%(asctime)s %(message)s',level=logging.DEBUG)

# Mandrill setup
mandrill_client = mandrill.Mandrill('hfhOUhj_5MyZZzF024sZqQ')

if(app.debug):
    from werkzeug.debug import DebuggedApplication
    app.wsgi_app = DebuggedApplication(app.wsgi_app, True)

@app.route('/')
def index():
    return "Hello world234!"

def parse_transcript_url(url):
    parsed = {}
    parsed["url"] = "http://parliament.wa.gov.au" + url

    matches = re.search("%20(?P<date>[0-9]{8})%20All\.pdf$", url)
    if matches:
        date = matches.groups("date")[0]
        tstruct = time.strptime(date, "%Y%m%d")
        parsed["date"] = datetime.fromtimestamp(mktime(tstruct))
    else:
        raise Exception("Failed parsing transcript URL \"%s\"", url)
    return parsed

def scrape_latest_transcripts():
    r = requests.get("http://parliament.wa.gov.au/hansard/hansard.nsf/DailyTranscripts")
    if(r.status_code == 404):
        raise Exception("DailyTranscripts 404 Not Found")
        return

    transcripts = {}
    anchors = BeautifulSoup(r.text).find('img', attrs={"alt": "Red diamond Icon"})\
            .find_parent("table")\
            .find_all(href=re.compile("\.pdf$"))
    for anchor in anchors:
        urlinfo = parse_transcript_url(anchor.get("href"))
        if(anchor.text == "Legislative Council"):
            transcripts["council"] = {"url": urlinfo["url"], "date": urlinfo["date"]}
        elif(anchor.text == "Legislative Assembly"):
            transcripts["assembly"] = {"url": urlinfo["url"], "date": urlinfo["date"]}
        else:
            raise Exception("Foreign \"red diamon\" link found. Matches neither Council nor Assembly")
    return transcripts

def search(transcript, search_term):
    if(transcript is None):
        return

    r = requests.get("http://parliament.wa.gov.au/hansard/hansard.nsf/NewAdvancedSearch?openform&Query="\
         + search_term + "&Fields=" + "(%5BHan_Date%5D=" + transcript["date"].strftime("%d/%m/%Y") + ")"\
         + "&sWord=fish&sMember=All%20Members&sHouse=Both%20Houses&sProc=All%20Proceedings&sPage=&sYear="\
         + "All%20Years&sDate=21/11/2013&sStartDate=&sEndDate=&sParliament=th&sBill=&sWordVar=1&sFuzzy=&"\
         + "sResultsPerPage=100&sResultsPage=1&sSortOrd=2&sAdv=1&sRun=true&sContinue=&sWarn=")
    
    results = []
    result_rows = BeautifulSoup(r.text).find("div", attrs={"id": "searchresults"}).find_all("tr")
    for tr in result_rows[1:]:
        cells = tr.find_all("td")

        page_range = cells[0].find("a").text.split(" / ")[1]
        pdf_url = "http://parliament.wa.gov.au" + cells[0].find("a").get("href")
        subject = cells[1].text
        house = cells[2].text.lower()
        members = cells[3].text.split(" | ")

        results.append({
            "page_range": page_range,
            "url": pdf_url,
            "subject": subject,
            "house": house,
            "members": members
        })
    return results

@app.route('/get_latest_transcripts')
def get_latest_transcripts():
    transcripts = scrape_latest_transcripts()
    if transcripts is not None:
        transcripts["assembly"]["date"] = transcripts["assembly"]["date"].strftime("%Y%m%d")
        transcripts["council"]["date"] = transcripts["council"]["date"].strftime("%Y%m%d")
        return json.dumps(transcripts)

def send_mail(results):
    # https://mandrillapp.com/api/docs/messages.python.html#method=send
    try:
        message = {
         'auto_html': None,
         'auto_text': None,
         'from_email': 'message.from_email@example.com',
         'from_name': 'HansardAlerts',
         'headers': {'Reply-To': 'message.reply@example.com'},
         'html': "<pre>" + json.dumps(results, indent=4) + "</pre>",
         'inline_css': None,
         'metadata': {'website': 'www.example.com'},
         'subject': 'HansardAlerts Alert',
         'to': [
            {'email': 'keithamoss@gmail.com',
             'name': 'Keith Moss',
             'type': 'to'},
            {'email': 'helen.ensikat@gmail.com',
             'name': 'Helen Ensikat',
             'type': 'to'}
         ],
         'track_clicks': None,
         'track_opens': None,
         'view_content_link': None}
        result = mandrill_client.messages.send(message=message, async=True)
        return result

    except mandrill.Error, e:
        # Mandrill errors are thrown as exceptions
        print 'A mandrill error occurred: %s - %s' % (e.__class__, e)
        # A mandrill error occurred: <class 'mandrill.UnknownSubaccountError'> - No subaccount exists with the id 'customer-123'    
        raise

@app.route('/search/<search_term>')
def search_debug(search_term):
    transcripts = scrape_latest_transcripts()
    if transcripts is not None and search_term is not None:
        results = search(transcripts["council"], search_term)
        send_mail(results)
        return json.dumps(results)

if __name__ == '__main__':
    app.run(host="0.0.0.0")
