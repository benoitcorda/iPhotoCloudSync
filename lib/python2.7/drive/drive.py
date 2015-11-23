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


logging.basicConfig(level = logging.WARNING,
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
	# Default directory to put the photos
	photoFolder = 'iPhotos'

	def __init__(self, PICKLE_CLIENT_SECRET = PICKLE_CLIENT_SECRET, CLIENT_SECRET_FILE = CLIENT_SECRET_FILE):
		"""Create an instance of GoogleDrive.

		Key Args:
			(you should set either of those)
			PICKLE_CLIENT_SECRET: file path where the credentials are picled.
			CLIENT_SECRET_FILE: secret data file to request credentials with.
		"""
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
		founds = self.ls(self.photoFolder)
		for f in self.ls(self.photoFolder):
			for p in f['parents']:
				if p['isRoot']:
					iPhoto_folder = f

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
	def ls(self, Name, folder_id = None):
		"""Retrieve a list of File metadata.

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
				param['q'] = "title contains '{name}'".format(name = Name)
				param['q'] += " and trashed=false"
				if folder_id is not None:
					param['q'] += " and '{id}' in parents".format(id = folder_id)
				files = self.service.files().list(**param).execute()

				result.extend(files['items'])
				page_token = files.get('nextPageToken')
				if not page_token:
					break
			except errors.HttpError, error:
				logging.error('An error occurred: %s' % error)
				break
		return result

	def exists(self, Name, folder_id = None):
		"""Test whether the file with Name exit in the directory with folder_id

		Args:
			name: the file name.
		Key Args:
			folder_id: directory's ID where the file is located [default: root dir].
		Returns:
			either None if nothing or return the file metadata.
		"""

		if not Name.startswith('gdrive/'):
			raise "Error GDrive path must start with  gdrive/"

		dirID = folder_id or self.rootDir['id']
		result = []
		page_token = None
		path = Name[6:] # remove 'gdrive'
		listOfDirs = [i for i in path.split(os.sep) if len(i) > 0]
		while len(listOfDirs) > 0:
			current = listOfDirs.pop(0)
			result = self.ls(current, folder_id = dirID)
			if len(result) == 0:
				return False
			if len(result) > 1:
				fileList = [i['title'] for i in result]
				logging.error("Ambigous result for Exist(%s)", path)
				logging.error('Exists routine got more than one result: %s, using first' % fileList)
			dirID = result[0]['id']

		if len(result) == 0:
			return False

		if len(result) == 1:
			return result[0]
		else:
			fileList = [i['title'] for i in result]
			logging.error('Exists call got more than one result: %s, returning first' % fileList)
			return result[0]

	def listdir(self, path, folder_id = None):
		"""List the content of a provided directory

		Args:
			path: path of directory to list
		Key Args:
			folder_id: directory's ID where the director is located [default: root dir].
		Returns:
			a list containing the names of the entries in the directory."""

		if not path.startswith('gdrive/'):
			raise "Error GDrive path must start with  gdrive/"

		dirID = folder_id or self.rootDir['id']
		result = []
		page_token = None
		gpath = path[6:] # remove 'gdrive'
		listOfDirs = [i for i in gpath.split(os.sep) if len(i) > 0]
		while len(listOfDirs) > 0:
			current = listOfDirs.pop(0)
			logging.debug("listdir current Dir {0}".format(current))
			result = self.ls(current, folder_id = dirID)
			logging.debug("listdir result Dir {0}".format(result))
			if len(result) > 0:
				dirID = result[0].get('id')
		#rebuild path from results
		files = self.ls('*', folder_id = dirID)
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
		logging.debug("Created Folder {0}".format(folder['title']))
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

		if not DirName.startswith('gdrive/'):
			raise "Error GDrive path must start with  gdrive/"

		if folder_id is None:
			folder_id = self.rootDir['id']

		gDirName = DirName[6:] # remove 'gdrive'
		listOfDirs = [i for i in gDirName.split(os.sep) if len(i) > 0]
		while len(listOfDirs) > 0:
			newDir = listOfDirs.pop(0)
			existDir = self.ls(newDir, folder_id=folder_id)
			if len(existDir) > 0:
				folder = existDir[0]
				folder_id = existDir[0]['id']
				logging.info("Dir {0} exists with id {1}, skipped".format(newDir, existDir[0]['id']))
				continue
			folder = self.mkdir(newDir, folder_id=folder_id)
			folder_id = folder['id']

		logging.debug("Created Folder {0}".format(DirName))
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
			logging.debug("File created {0} inside {1}".format(title, body['parents']))
			return file
		except errors.HttpError, error:
			logging.error('An error occured: %s' % error)
			return None

	def copy2(self, source, target, folder_id = None):
		print "s",source, "tar",target
		filename = os.path.basename(target)
		dirname =  os.path.dirname(target)
		folder = self.exists(dirname)
		mime_type = mimetypes.types_map[os.path.splitext(filename)[-1]]
		print folder['id']
		print (filename, folder['id'], mime_type)
		self.insert(source, title = filename, folder_id = folder['id'], mime_type = mime_type)

	def stat(self, FileName, folder_id = None):
		raise "WARNING not implemented GDrive stat",FileName
		logging.error("stat not implement for Gdrive {0}".format(FileName))
		#raise Exception("Not ready yet")

	def getsize(self, FileName, folder_id = None):
		raise "Not ready yet"

	def remove(self, FileName, folder_id = None):
		raise "Not ready yet"

	def rmdir(self, DirName, folder_id = None):
		raise "Not ready yet"

api = Drive(PICKLE_CLIENT_SECRET=PICKLE_CLIENT_SECRET)
