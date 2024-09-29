import platform, os, sys, stat, tempfile, re, subprocess
from browserstack.bserrors import BrowserStackLocalError
import gzip

try:
    import urllib.request

    def urlopen(url, headers=None):
        return urllib.request.urlopen(urllib.request.Request(url, headers=headers))
except ImportError:
    import urllib2

    def urlopen(url, headers=None):
        return urllib2.urlopen(urllib2.Request(url, headers=headers))

class LocalBinary:
  _version = None

  def __init__(self):
    is_64bits = sys.maxsize > 2**32
    self.is_windows = False
    osname = platform.system()
    source_url = "https://www.browserstack.com/local-testing/downloads/binaries/"
    if os.environ.get('BROWSERSTACK_LOCAL_BIN_URL'):
      source_url = os.environ.get('BROWSERSTACK_LOCAL_BIN_URL')

    if osname == 'Darwin':
      self.http_path = source_url + "BrowserStackLocal-darwin-x64"
    elif osname == 'Linux':
      if self.is_alpine():
        self.http_path = source_url + "BrowserStackLocal-alpine"
      else:
        if is_64bits:
          self.http_path = source_url + "BrowserStackLocal-linux-x64"
        else:
          self.http_path = source_url + "BrowserStackLocal-linux-ia32"
    else:
      self.is_windows = True
      self.http_path = source_url + "BrowserStackLocal.exe"

    self.ordered_paths = [
      os.path.join(os.path.expanduser('~'), '.browserstack'),
      os.getcwd(),
      tempfile.gettempdir()
    ]
    self.path_index = 0

  @staticmethod
  def set_version(version):
    LocalBinary._version = version

  def is_alpine(self):
    response = subprocess.check_output(["grep", "-w", "NAME", "/etc/os-release"])
    return response.decode('utf-8').find('Alpine') > -1

  def __make_path(self, dest_path):
    try:
      if not os.path.exists(dest_path):
        os.makedirs(dest_path)
      return True
    except:
      return False

  def __available_dir(self):
    while self.path_index < len(self.ordered_paths):
      if self.__make_path(self.ordered_paths[self.path_index]):
        final_path = self.ordered_paths[self.path_index]
        self.path_index += 1
        return final_path
      else:
        self.path_index += 1
    raise BrowserStackLocalError('Error trying to download BrowserStack Local binary')

  def download(self, chunk_size=8192, progress_hook=None):
    headers = {
      'User-Agent': '/'.join(('browserstack-local-python', LocalBinary._version)),
      'Accept-Encoding': 'gzip, *',
    }

    if sys.version_info < (3, 2):
      # lack of support for gzip decoding for stream, response is expected to have a tell() method
      # https://www.enricozini.org/blog/2011/cazzeggio/python-gzip/
      headers.pop('Accept-Encoding', None)

    response = urlopen(self.http_path, headers=headers)
    try:
      total_size = int(response.info().get('Content-Length', '').strip() or '0')
    except:
      total_size = int(response.info().get_all('Content-Length')[0].strip() or '0')
    bytes_so_far = 0

    dest_parent_dir = self.__available_dir()
    dest_binary_name = 'BrowserStackLocal'
    if self.is_windows:
      dest_binary_name += '.exe'

    content_encoding = response.info().get('Content-Encoding', '')
    gzip_file = gzip.GzipFile(fileobj=response, mode='rb') if content_encoding.lower() == 'gzip' else None

    if os.getenv('BROWSERSTACK_LOCAL_DEBUG_GZIP') and gzip_file:
      print('using gzip in ' + headers['User-Agent'])

    def read_chunk(chunk_size):
      if gzip_file:
        return gzip_file.read(chunk_size)
      else:
        return response.read(chunk_size)

    with open(os.path.join(dest_parent_dir, dest_binary_name), 'wb') as local_file:
      while True:
        chunk = read_chunk(chunk_size)
        bytes_so_far += len(chunk)

        if not chunk:
          break

        if total_size > 0 and progress_hook:
          progress_hook(bytes_so_far, chunk_size, total_size)

        try:
          local_file.write(chunk)
        except:
          return self.download(chunk_size, progress_hook)

    if gzip_file:
      gzip_file.close()

    if callable(getattr(response, 'close', None)):
      response.close()

    final_path = os.path.join(dest_parent_dir, dest_binary_name)
    st = os.stat(final_path)
    os.chmod(final_path, st.st_mode | stat.S_IXUSR)
    return final_path

  def __verify_binary(self,path):
    try:
      binary_response = subprocess.check_output([path,"--version"]).decode("utf-8")
      pattern = re.compile("BrowserStack Local version \d+\.\d+")
      return bool(pattern.match(binary_response))
    except:
      return False

  def get_binary(self):
    dest_parent_dir = os.path.join(os.path.expanduser('~'), '.browserstack')
    if not os.path.exists(dest_parent_dir):
      os.makedirs(dest_parent_dir)
    binary_name = 'BrowserStackLocal.exe' if self.is_windows else 'BrowserStackLocal'
    bsfiles = [f for f in os.listdir(dest_parent_dir) if f == binary_name]

    if len(bsfiles) == 0:
      binary_path = self.download()
    else:
      binary_path = os.path.join(dest_parent_dir, bsfiles[0])

    valid_binary = self.__verify_binary(binary_path)
    if valid_binary:
      return binary_path
    else:
      binary_path = self.download()
      valid_binary = self.__verify_binary(binary_path)
      if valid_binary:
        return binary_path
      else:
        raise BrowserStackLocalError('BrowserStack Local binary is corrupt')

