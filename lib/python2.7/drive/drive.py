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

#################
## Consts
#################
# Location of the client secrets.
CLIENT_SECRET_FILE = 'client_secrets.json'
# pickled secret data (it's tedious)
PICKLE_CLIENT_SECRET = 'credentials.pkl'

#authenticate
import hashlib
import logging
import pickle
import os
import os.path
import httplib2
import apiclient.discovery
import apiclient.http
import oauth2client.client
from apiclient import errors
import hashlib

logging.basicConfig(level = logging.DEBUG)

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

	def __init__(self, PICKLE_CLIENT_SECRET = None, CLIENT_SECRET_FILE = None):
		"""Create an instance of GoogleDrive.

		Key Args:
			(you should set either of those)
			PICKLE_CLIENT_SECRET: file path where the credentials are picled.
			CLIENT_SECRET_FILE: secret data file to request credentials with.
		"""
		if PICKLE_CLIENT_SECRET:
			self.credentials = pickle.load(open(PICKLE_CLIENT_SECRET, 'rb'))
		elif CLIENT_SECRET_FILE:
			self.getCredentials(CLIENT_SECRET_FILE)
			self.pickleCrendetials()

		self.oauth()

		# go to iPhoto folder
		founds = self.ls(self.photoFolder)
		if len(founds) > 0:
			self.rootDir = founds[0]
		else:
			self.rootDir = self.mkdir(self.photoFolder)
			

	def pickleCrendetials(self):
		pickle.dump(credentials, open('credentials.pkl' , 'wb'))
		logging.debug("credentials saved into 'credentials.pkl'")

	def getCredentials(self, CLIENT_SECRET_FILE):
		"""Obtain the google drive crendtial from the web

		Args:
			CLIENT_SECRET_FILE: file path of the json file containing the secret info.
		"""
		# Perform OAuth2.0 authorization flow.
		flow = oauth2client.client.flow_from_clientsecrets(CLIENT_SECRET_FILE, self.OAUTH2_SCOPE)
		flow.redirect_uri = oauth2client.client.OOB_CALLBACK_URN
		authorize_url = flow.step1_get_authorize_url()
		print 'Go to the following link in your browser: ' + authorize_url
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

		dirID = folder_id or self.rootDir['id']
		result = []
		page_token = None
		listOfDirs = [i for i in Name.split(os.sep) if len(i) > 0]
		while len(listOfDirs) > 0:
			current = listOfDirs.pop(0)
			result = self.ls(current, folder_id = dirID)
			if len(result) == 0:
				return False
			elif len(result) > 1:
				fileList = [i['title'] for i in result]
				logging.error('Exists call got more than one result: %s, using first' % fileList)

			dirID = result[0]['id']

		if len(result) == 1:
			return True
		elif len(result) == 0:
			return False
		else:
			fileList = [i['title'] for i in result]
			logging.error('Exists call got more than one result: %s, returning first' % fileList)
			return True

	def listdir(self, path, folder_id = None):
		"""List the content of a provided directory

		Args:
			path: path of directory to list
		Key Args:
			folder_id: directory's ID where the director is located [default: root dir].
		Returns:
			a list containing the names of the entries in the directory."""
		dirID = folder_id or self.rootDir['id']
		result = []
		page_token = None
		listOfDirs = [i for i in path.split(os.sep) if len(i) > 0]
		while len(listOfDirs) > 0:
			current = listOfDirs.pop(0)
			print "current",current
			result = self.ls(current, folder_id = dirID)
			print 'res',result
			if len(result) > 0:
				dirID = result[0].get('id')
		#rebuild path from results
		files = self.ls('*', folder_id = dirID)
		return [os.path.join(path,i['title']) for i in files]

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
		if folder_id is None:
			folder_id = self.rootDir['id']

		listOfDirs = [i for i in DirName.split(os.sep) if len(i) > 0]
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

api = Drive(PICKLE_CLIENT_SECRET=os.path.join('Sandbox',PICKLE_CLIENT_SECRET))
