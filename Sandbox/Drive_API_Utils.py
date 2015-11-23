#!/usr/bin/python
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
	def uploadFile(self, filename, folder = None, folder_id = None, mime_type = '*/*'):
		"""upload new file if not already present (md5sum check).

		Args:
			filename: Full file path of the file to insert.
		Key Args:
			folder: drive path from root of the folder to upload the file into.
			folder_id: ID of the folder to upload the file into.
		Returns:
			Inserted file metadata if successful, None otherwise.
		"""
		# Set the parent folder.
		parentName, fileTitleName = os.path.split(filename)
		parentDir = None
		if len(folder) > 0:
			parentDir = self.mkdirp(folder)

		existingFile = self.exists(fileTitleName, folder_id = parentDir.get('id'))
		if existingFile is not None:
			logging.debug("Existing file found md5 %s" % existingFile['md5Checksum'])
			localFileHash = hashlib.md5(open(filename).read()).hexdigest()
			if localFileHash == existingFile['md5Checksum']:
				logging.debug("File already upload skipping...")
				return existingFile

		newFile = self.insert(filename,
			title = fileTitleName,
			folder_id = parentDir['id'] or folder_id,
			mime_type = mime_type)

		logging.debug("uploadImage %s" % newFile)
		return newFile

	def uploadImage(self, filename, folder = None, folder_id = None):
		"""upload new image if not already present (md5sum check).

		Args:
			filename: Full file path of the img to insert.
		Key Args:
			folder: drive path from root of the folder to upload the img into.
			folder_id: ID of the folder to upload the img into.
		Returns:
			Inserted file metadata if successful, None otherwise.
		"""
		return self.uploadFile(filename,
			folder = folder,
			folder_id = folder_id,
			mime_type = 'image/jpeg')

	def uploadVideo(self, filename, folder = None, folder_id = None):
		"""upload new video if not already present (md5sum check).

		Args:
			filename: Full file path of the video to insert.
		Key Args:
			folder: drive path from root of the folder to upload the video into.
			folder_id: ID of the folder to upload the video into.
		Returns:
			Inserted file metadata if successful, None otherwise.
		"""
		return self.uploadFile(filename,
			folder = folder,
			folder_id = folder_id,
			mime_type = 'video/mp4')

	def delete(self, file_id):
		"""Remove a file.

		Args:
			file_id: ID of the file to remove from the folder.
		"""
		try:
   			self.service.files().delete(fileId=file_id).execute()
  		except errors.HttpError, error:
			logging.error('An error occurred: %s' % error)

	def delete_from_filename(self, fileNane, folder_id = None):
		"""Remove a file.

		Args:
			fileNane: ID of the file to remove from the folder.
		Key Args:
			folder_id: ID of the folder to remove the file from.
		"""
		result = self.ls(fileNane, folder_id = folder_id)
		if len(result) == 1:
			self.delete(result[0]['id'])
			logging.debug("Found file %s, deleted" % result[0]['title'])
		elif len(result) > 1:
			logging.error("Found several files %s can't delete many" % [i['title'] for i in result])
		else:
			logging.info("Found several files %s can't delete many" % [i['title'] for i in result])


if __name__ == "__main__":
    drive = Drive(PICKLE_CLIENT_SECRET=PICKLE_CLIENT_SECRET)
    #file = drive.insert("../allo.png")
    #drive.delete(file['id'])
    #drive.uploadImage("file.png",folder="album1/event1")
    #deletete all: [drive.delete(i['id']) for i in drive.ls('*')]

