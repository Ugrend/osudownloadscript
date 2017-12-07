import requests
import time
from http.cookiejar import LWPCookieJar
import os
import shutil
import re
import zipfile

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:58.0) Gecko/20100101 Firefox/58.0"
RE_SEARCH = re.compile('/s/(\d+)')

OSU_USER = os.environ["OSU_USERNAME"]
OSU_PASSWORD = os.environ["OSU_PASSWORD"]
DOWNLOAD_PATH = os.environ["OSU_DOWNLOAD_DIR"]
EXTRACT_PATH = os.environ["OSU_EXTRACT_DIR"]


class NotLoggedIn(Exception):
    pass


class SessionHandler():
    def __init__(self, username, password):
        self.session_expires = None
        self.session = requests.Session()
        self.session.cookies = LWPCookieJar('cookies')
        if not os.path.exists('cookies'):
            self.save()
        else:
            self.session.cookies.load()
            try:
                self.session_expires = max([cookie.expires or 1 for cookie in self.session.cookies])
            except ValueError:
                pass

        self.username = username
        self.password = password
        self._headers = {
            'User-Agent': USER_AGENT
        }

    def save(self):
        self.session.cookies.save()

    def has_expired(self):
        if self.session_expires and self.session_expires < int(time.time()):
            return True
        if self.session_expires:
            return False
        return True

    def create_session(self):
        self.session.post('https://osu.ppy.sh/forum/ucp.php?mode=login', headers=self._headers, data={
            'username': self.username,
            'password': self.password,
            'redirect': 'index.php',
            'sid': None,
            'login': 'Login'
        })
        self.save()
        self.session_expires = max([cookie.expires or 1 for cookie in self.session.cookies])

    def get_session(self) ->requests.Session:
        if self.has_expired():
            self.create_session()
        return self.session

    def get(self, url, stream=False)-> requests.Response:
        return self.get_session().get(url, stream=stream, headers=self._headers)

    def head(self,url)-> requests.Response :
        return self.get_session().head(url, headers=self._headers)


class Downloader:
    def __init__(self, session: SessionHandler):
        self.session = session

    def get_file_name(self, true_url):
        headers = self.session.head(true_url).headers
        return headers['Content-Disposition'].split(';')[1].split('=')[1].replace('"', '')

    def get_true_url(self, url):
        headers = self.session.head(url).headers
        try:
            if 'http://osu.ppy.sh/forum/ucp.php' in headers['Location']:
                raise NotLoggedIn("Got login Screen Redirect")
        except KeyError:
            return False
        return headers['Location']

    def download_map(self, url):
        print("Downloading %s" % url, flush=True)
        try:
            download_url = self.get_true_url(url)
        except NotLoggedIn:
            # try log in again throw if continues to fail
            self.session.create_session()
            download_url = self.get_true_url(url)

        filename = os.path.join(DOWNLOAD_PATH, self.get_file_name(download_url))
        r = self.session.get(download_url, stream=True)
        with open(filename + '.part', 'wb') as f:
            shutil.copyfileobj(r.raw, f)
        shutil.move(filename + '.part', filename)
        print("Downloaded %s" % filename, flush=True)
        return filename


def get_map_ids(session: SessionHandler = None, page=1)->list:
    url = "https://osu.ppy.sh/p/beatmaplist?l=1&r=0&q=&g=0&la=0&ra=&s=4&o=1&m=0&page=%s" %page

    if session:
        page = session.get(url).text
    else:
        page = requests.get(url, headers={'User-Agent': USER_AGENT}).text
    return [r.group(1) for r in re.finditer(RE_SEARCH,page)]


def extract_zip(file_path):
    folder_name = os.path.splitext(os.path.basename(file_path))[0]
    extract_to = os.path.join(EXTRACT_PATH, folder_name)
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)
    print("Extracting %s to %s" % (file_path, extract_to), flush=True)
    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)


if __name__ == "__main__":
    log = open("downloaded.txt", "a+")
    log.seek(0, 0)
    ignore_list = [x.strip() for x in log.readlines()]
    session = SessionHandler(OSU_USER, OSU_PASSWORD)
    downloader = Downloader(session)
    for x in range(1, 5):
        for map_set in get_map_ids(session, page=x):
            if map_set not in ignore_list:
                try:
                    downloaded_map = downloader.download_map("https://osu.ppy.sh/d/%s" % map_set)
                    extract_zip(downloaded_map)
                    ignore_list.append(map_set)
                    log.write(map_set + '\n')
                    log.flush()
                except Exception as e:
                    print("ERROR: Failed to download map %s Error: %s" % (map_set, str(e)), flush=True)
    log.close()
