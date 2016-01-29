#!/usr/bin/env python
"""Reads iPhoto library info, and exports photos and movies to Google Drive."""

# Copyright 2015 Google Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


import hashlib
import logging
import mimetypes
import pickle
import os
import sys
import os.path
import httplib2
import apiclient.discovery
import apiclient.http
import oauth2client.client
from apiclient import errors
import hashlib

#################
## Consts
#################
# Location of the client secrets.
CUR_DIR = os.path.dirname(os.path.realpath(__file__))
CLIENT_SECRET_FILE = os.path.join(CUR_DIR,'client_secrets.json')
# pickled secret data (it's tedious)
PICKLE_CLIENT_SECRET = os.path.join(CUR_DIR,'credentials.pkl')
# pickled secret data (it's tedious)
CACHE_FILE = os.path.join(CUR_DIR,'cache.pkl')


logging.basicConfig(stream=sys.stdout, level = logging.WARNING,
					format = '%(asctime)s - %(filename)s %(lineno)d - %(levelname)s - %(message)s')

# from https://docs.python.org/2/howto/logging-cookbook.html
# create logger with 'drive'
logger = logging.getLogger('Gdrive')
logger.setLevel(logging.DEBUG)
# create console handler with a higher log level
# ch = logging.StreamHandler()
# ch.setLevel(logging.DEBUG)
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# ch.setFormatter(formatter)
# logger.addHandler(ch)

mimetypes.init()

class Drive:
	# OAuth 2.0 scope that will be authorized.
	# Check https://developers.google.com/drive/scopes for all available scopes.
	OAUTH2_SCOPE = 'https://www.googleapis.com/auth/drive.file'
	# credentials to authorize request
	credentials = None
	# Drive API service instance.
	service = None
	# ParentId of the root directory, to keep track of where we are.
	rootDir = None
	# Hardcoded prefix refering to google drive root directory. (make sure to end with '/' if you change this!)
	prefix = 'gdrive/'
	# Default directory to put the photos
	photoFolder = 'iPhotos'
	# File to keep the list of uploaded files with their checksums.
	checksumCacheFileName = prefix + 'checksum.appcache'

	def __init__(self, PICKLE_CLIENT_SECRET = PICKLE_CLIENT_SECRET, CLIENT_SECRET_FILE = CLIENT_SECRET_FILE):
		"""Create an instance of GoogleDrive.

		Key Args:
			(you should set either of those)
			PICKLE_CLIENT_SECRET: file path where the credentials are picled.
			CLIENT_SECRET_FILE: secret data file to request credentials with.
		"""
		self._checksumcache = None
		try:
			if (not os.path.isfile(PICKLE_CLIENT_SECRET)):
				raise FileNotFoundError("No Auth Token")
			self.credentials = pickle.load(open(PICKLE_CLIENT_SECRET, 'rb'))
		except Exception, e:
			logging.info("PHotoShare needs Drive Authentication to Upload Files {0}".format(CLIENT_SECRET_FILE))
			self.getCredentials(CLIENT_SECRET_FILE)
			self.pickleCrendetials()

		self.oauth()

		# go to iPhoto folder
		iPhoto_folder = None
		for f in self._ls(self.photoFolder):
			for p in f['parents']:
				if p['isRoot']:
					iPhoto_folder = f
					break
			if iPhoto_folder is not None:
				break

		logging.debug("found iPhoto_folder {0}".format(iPhoto_folder))

		if iPhoto_folder is not None:
			self.rootDir = iPhoto_folder
		else:
			self.rootDir = self.mkdir(self.photoFolder)

	def pickleCrendetials(self):
		if self.credentials is not None:
			pickle.dump(self.credentials, open(PICKLE_CLIENT_SECRET , 'wb'))
			logging.debug("credentials saved into 'credentials.pkl'")
		else:
			logging.error("credentials is None can't dump into file")

	def getCredentials(self, CLIENT_SECRET_FILE):
		"""Obtain the google drive crendtial from the web

		Args:
			CLIENT_SECRET_FILE: file path of the json file containing the secret info.
		"""
		# Perform OAuth2.0 authorization flow.
		flow = oauth2client.client.flow_from_clientsecrets(CLIENT_SECRET_FILE, self.OAUTH2_SCOPE)
		flow.redirect_uri = oauth2client.client.OOB_CALLBACK_URN
		authorize_url = flow.step1_get_authorize_url()

		logging.warning("Go to the following link in your browser: {0}".format(authorize_url))
		code = raw_input('Enter verification code: ').strip()
		self.credentials = flow.step2_exchange(code)

	def fetchCheckSumCache(self):
		"""Download and parse the checksumCacheFile from GDrive"""
		content = self.wget(self.checksumCacheFileName)
		try:
			import cPickle as pickle
		except:
			import pickle
		try:
			return pickle.loads(content)
		except Exception as e:
			logging.error("Couldn't fetch checksumcache, error: %s" % e)
			import traceback
			logging.error(traceback.format_exc())
			return None

	def getCheckSumCache(self):
		"""Fetch the checksumCache file and return the content or empty dictionary is not found"""
		if self._checksumcache is not None:
			return self._checksumcache
		self._checksumcache = self.fetchCheckSumCache()
		if not self._checksumcache:
			self.rebuildCheckSumCache()
		return self._checksumcache or {}

	def rebuildCheckSumCache(self):
		"""List all the files under iPhoto folder on Gdrive and store checksums into cache.
		Cache file will be uploaded on GDrive
		"""
		queue = [(self.rootDir, self.prefix)]
		cache = {}
		logging.warning("Rebuilding checksumcache...")
		emptyFolderCount = 0
		nonemptyFolderCount = 0
		mediaCount = 0
		while len(queue) > 0:
			curDir, path = queue.pop(0)
			curFid = curDir['id']
			results = self._ls('*', folder_id = curFid)
			if len(results) == 0:
				emptyFolderCount +=1
			logging.debug('%s found %d elements' % (path, len(results)))
			checksums = {}
			for elm in results:
				if elm['mimeType'] == 'application/vnd.google-apps.folder':
					queue.append((elm, os.path.join(path,elm['title'])))
				elif 'image' in elm['mimeType'] or 'video' in elm['mimeType']:
					checksums[elm['title']] = elm['md5Checksum']
			if len(checksums) > 0:
				nonemptyFolderCount +=1
				mediaCount += len(checksums)
				cache[path] = checksums
		logging.debug("Found %d empty folders %d folders with medias, with %d files total" %(emptyFolderCount, nonemptyFolderCount, mediaCount))
		logging.debug("Checksumcache rebuilt uploading...")
		self._checksumcache = cache
		self.updateCheckSumCache()

	def updateCheckSumCache(self, new_cache = None):
		"""Update the checksumCacheFileName the checksumCache file

		Args:
			new_cache: new content to replace with, if None default is self.checksumCache,
			           if you provide new_cache we will also override self.checksumCache.
		"""
		try:
			import cPickle as pickle
		except:
			import pickle
		if new_cache is None:
			new_cache = self.getCheckSumCache()
		else:
			if type(new_cache) != dict:
				logging.error("updateCheckSumCache error: you must provide a valid dictionary")
				return
			self._checksumcache = new_cache
		if new_cache is None:
			logging.warning("Can't updateCheckSumCache no content provided/found please provide 'new_cache' argument")
			return
		try:
			with open(CACHE_FILE, 'wb') as handle:
				pickle.dump(new_cache, handle, pickle.HIGHEST_PROTOCOL)
			# remove old one.
			if self.exists(self.checksumCacheFileName) and os.path.exists(CACHE_FILE):
				self.remove(self.checksumCacheFileName)
			# upload to gdrive.
			self.copy2(CACHE_FILE, self.checksumCacheFileName)
		finally:
			if os.path.exists(CACHE_FILE):
				os.remove(CACHE_FILE)
				logging.debug("removed %s" % CACHE_FILE)
		# try to fetch is from GDrive, just to be safe
		if self.fetchCheckSumCache() is None:
			logging.error("updateCheckSumCache failed, retrying...")
			self.updateCheckSumCache(new_cache = new_cache)

	def oauth(self):
		"""Create an authorized Drive API client service."""
		assert self.credentials is not None
		http = httplib2.Http()
		self.credentials.authorize(http)
		self.service = apiclient.discovery.build('drive', 'v2', http=http)
		assert self.service is not None

	################
	# file functions
	################
	def _ls(self, Name, folder_id = None):
		"""Retrieve a list of File metadata when providing the folder_id.

		Args:
			name: the string to search for.
		Key Args:
			folder_id: Parent folder's ID.
		Returns:
			List of Files metadata.
		"""
		result = []
		page_token = None
		while True:
			try:
				param = {}
				if page_token:
					param['pageToken'] = page_token
				param['q'] = u"title contains '{name}'".format(name = Name)
				param['q'] += " and trashed=false"
				if folder_id is not None:
					param['q'] += u" and '{id}' in parents".format(id = folder_id)
				files = self.service.files().list(**param).execute()

				result.extend(files['items'])
				page_token = files.get('nextPageToken')
				if not page_token:
					break
			except errors.HttpError, error:
				logging.error('An error occurred: %s' % error)
				break
		return result

	def ls(self, path, folder_id = None):
		"""Retrieve a list of File metadata (e.g. gdrive/a/b/*.jpg).

		Args:
			path: the string to search for based on absolute path.
		Key Args:
			folder_id: directory's ID where the relative path starts at, if not provided you must start the path with gdrive/
		Returns:
			List of Files metadata (empty list if no result).
		"""

		if folder_id is None and not path.startswith(self.prefix):
			raise NameError("Error GDrive path must start with  '%s' or you need to provide a folder_id" % self.prefix)

		result = []
		page_token = None
		if path.startswith(self.prefix):
			gpath = path[len(self.prefix)-1:] # remove prefix without ending slash
		else:
			gpath = path
		listOfDirs = [i for i in gpath.split(os.sep) if len(i) > 0]
		dirID = folder_id or self.rootDir['id']
		if len(listOfDirs) == 0:
			listOfDirs = ['*']
		# go down the directory tree while having subdirectories
		while len(listOfDirs) > 1:
			current = listOfDirs.pop(0)
			logging.debug(u"ls current Dir {0}".format(current))
			result = self._ls(current, folder_id = dirID)
			logging.debug(u"ls result Dir {0}".format(result))
			if len(result) > 0:
				dirID = result[0].get('id')
			else:
				logging.warning('Path not found while trying to run ls for: %s' % path)
				return []
		return self._ls(listOfDirs.pop(0), folder_id = dirID)

	def exists(self, Name, folder_id = None):
		"""Test whether the file with Name exit in the directory with folder_id

		Args:
			name: the file name.
		Key Args:
			folder_id: directory's ID where the file is located [default: root dir].
		Returns:
			either None if nothing or return the file metadata.
		"""

		if Name == self.prefix[:-1] and folder_id is None:
			return self.rootDir

		result = self.ls(Name, folder_id = folder_id)

		if len(result) == 0:
			return False

		if len(result) == 1:
			return result[0]
		else:
			fileList = [i['title'] for i in result]
			logging.error("Exists call '%s' got more than one result: %s, returning first" % (Name, fileList))
			return result[0]

	def listdir(self, path, folder_id = None):
		"""List the content of a provided directory

		Args:
			path: path of directory to list
		Key Args:
			folder_id: directory's ID where the director is located [default: root dir].
		Returns:
			a list containing the names of the entries in the directory."""

		# treat the root dir as special case
		if (path == self.prefix[:-1] or path == self.prefix) and folder_id is None:
			files = self._ls('*', folder_id = self.rootDir['id'])
			return [i['title'] for i in files]

		result = self.ls(path, folder_id = folder_id)
		if len(result) == 0:
			logging.error('Path not found while trying to run listdir for: %s' % path)
			return []
		#rebuild path from results
		files = self._ls('*', folder_id = result[0]['id'])
		return [i['title'] for i in files]

	def mkdir(self, DirName, folder_id = None):
		"""Create a directory inside Dir with folder_id (root is the default).

		Args:
			DirName: directory name.
		Key Args:
			folder_id: Parent folder's ID.
		Returns:
			Inserted directory metadata if successful, None otherwise.
		"""
		body = {
			'title': DirName,
			'parents': 'root',
			'mimeType': 'application/vnd.google-apps.folder'
		}
		if folder_id is not None:
			body["parents"] = [{"id" : folder_id}]
		elif self.rootDir is not None:
			body["parents"] = [{"id" : self.rootDir['id']}]
		folder = self.service.files().insert(body = body).execute()
		logging.debug(u"Created Folder {0}".format(folder['title']))
		return folder

	def makedirs(self, DirName, folder_id = None):
		"""create a leaf directory and all intermediate ones.
		Works like mkdir, except that any intermediate path segment (not
		just the rightmost) will be created if it does not exist.  This is
		recursive..
		(e.g. self.mkdirp('iPhoto/album1/event1'))

		Args:
			DirName: full path of the directory name.
		Returns:
			Inserted directory metadata if successful, None otherwise.
		"""

		if not DirName.startswith(self.prefix) and folder_id is None:
			raise NameError("Error GDrive path must start with '%s'" % self.prefix)


		if folder_id is None:
			folder_id = self.rootDir['id']

		if DirName.startswith(self.prefix):
			gDirName = DirName[len(self.prefix)-1:] # remove prefix without ending slash
		else:
			gDirName = DirName
		listOfDirs = [i for i in gDirName.split(os.sep) if len(i) > 0]
		while len(listOfDirs) > 0:
			newDir = listOfDirs.pop(0)
			existDir = self._ls(newDir, folder_id=folder_id)
			if len(existDir) > 0:
				folder = existDir[0]
				folder_id = existDir[0]['id']
				logging.info(u"Dir {0} exists with id {1}, skipped".format(newDir, existDir[0]['id']))
				continue
			folder = self.mkdir(newDir, folder_id=folder_id)
			folder_id = folder['id']

		logging.debug(u"Created Folder {0}".format(DirName))
		return folder

	def insert(self, file_path, title = None, description = None, folder_id = None, mime_type = '*/*'):
		"""Insert new file.

		Args:
			file_path: full path of the file to insert.
		Key Args:
			title: Title of the file to insert, including the extension.
			description: Description of the file to insert.
			folder_id: ID of the folder to add the file into.
			mime_type: MIME type of the file to insert.
		Returns:
			Inserted file metadata if successful, None otherwise.
		"""
		dirID = folder_id or self.rootDir['id']

		try:
			media_body = apiclient.http.MediaFileUpload(file_path,
														mimetype = mime_type,
														resumable = True)
		except IOError as e:
			logging.error('error occured while reading file: %s' % e)
			raise e

		title = title or file_path
		body = {
			'title': title,
			'description': description,
			'mimeType': mime_type
		}

		if folder_id is None:
			raise "you must provide folder_id"

		body['parents'] = [{'id': folder_id}]

		try:
			file = self.service.files().insert(
			    body = body,
			    media_body = media_body).execute()
			logging.debug(u"File created {0} inside {1}".format(title, body['parents']))
			return file
		except errors.HttpError, error:
			logging.error('An error occured: %s' % error)
			return None

	def copy2(self, source, target, folder_id = None):
		filename = os.path.basename(target)
		dirname =  os.path.dirname(target)
		folder = self.exists(dirname)
		if not folder and folder_id is None:
			logging.error("Can't copy: Folder doesn't exist, you need to mkdir '%s' beforehand" % dirname)
			return None
		mime_type = mimetypes.types_map[os.path.splitext(filename)[-1]]
		if folder_id is None:
			folder_id = folder['id']

		newFile = self.insert(source, title = filename, folder_id = folder_id, mime_type = mime_type)

		if newFile is not None:
			dirCache = self.getCheckSumCache().get(dirname,{})
			dirCache[newFile['title']] = newFile['md5Checksum']
			self._checksumcache[dirname] = dirCache


	def wget(self, source, folder_id = None):
		"""Download a file's and return its content.

		Args:
		source: absolute path in gdrive/ or relative with folder_id.

		Returns:
		File's content if successful, None otherwise.
		"""
		result = self.ls(source, folder_id = folder_id)
		if len(result) == 0:
			return None
		download_url = result[0]['downloadUrl']
		if download_url:
			resp, content = self.service._http.request(download_url)
			if resp.status == 200:
				logging.debug("wget Status: %s" % resp)
				return content
			else:
				logging.error("An error occurred while downloading file '%s'" % resp)
				return None

	def remove(self, FileName, folder_id = None, file_id = None):
		"""Remove a file.

		Args:
			FileName: path of the file to delete (absolute if folder_id not provided e.g. 'gdrive/foobar.txt').
			folder_id: ID of the folder to remove the FileName (FileName is relative path).
			file_id: ID of the file to remove from the folder, if file_id is provided the previous two are ignored.
		"""
		if folder_id is None:
			folder_id = self.rootDir['id']
		if file_id is None:
			result = self.ls(FileName, folder_id = folder_id)
			if len(result) == 1:
				file_id = result[0].get('id')
			if len(result) > 1:
				logging.error("Ambigous results for deleting '%s', operation cancelled." % FileName)
				return
		if file_id is not None:
			try:
				self.service.files().delete(fileId=file_id).execute()
				filename = os.path.basename(FileName)
				dirname =  os.path.dirname(FileName)
				dirCache = self.getCheckSumCache().get(dirname,{})
				if dirCache:
					dirCache.pop(filename, None)
			except errors.HttpError, error:
				logging.error('An error occurred: %s' % error)
		else:
			logging.error("Can't remove  '%s' or '%s' reason:not found, operation cancelled." % (FileName, file_id))

	def rmdir(self, DirName, folder_id = None):
		raise "Not ready yet"

	def getsize(self, FileName, folder_id = None):
		raise "Not ready yet"

	def stat(self, FileName, folder_id = None):
		raise "WARNING not implemented GDrive stat " + FileName

api = Drive(PICKLE_CLIENT_SECRET=PICKLE_CLIENT_SECRET)
