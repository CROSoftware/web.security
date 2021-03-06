# encoding: utf-8

from __future__ import unicode_literals

from hashlib import md5, sha256
from hmac import new as hmac
from binascii import unhexlify
from os import getpid
from socket import gethostname
from time import time
from random import randint
from threading import RLock

from web.core.compat import py3, str, unicode

try:
	from hmac import compare_digest
except ImportError:
	def compare_digest(a, b):
		return a == b


log = __import__('logging').getLogger(__name__)

MACHINE = int(md5(gethostname().encode() if py3 else gethostname()).hexdigest()[:6], 16)


class SignatureError(ValueError):
	pass


class Counter(object):
	def __init__(self):
		self.value = randint(0, 2**24)
		self.lock = RLock()
	
	def __iter__(self):
		return self
	
	def __next__(self):
		with self.lock:
			self.value = (self.value + 1) % 0xFFFFFF
			value = self.value
		
		return value
	
	next = __next__

counter = Counter()


class SessionIdentifier(object):
	def __init__(self, value=None):
		if value:
			self.parse(value)
		else:
			self.generate()
	
	def parse(self, value):
		self.time = int(value[:8], 16)
		self.machine = int(value[8:14], 16)
		self.process = int(value[14:18], 16)
		self.counter = int(value[18:24], 16)
	
	def generate(self):
		self.time = int(time())
		self.machine = MACHINE
		self.process = getpid() % 0xFFFF
		self.counter = next(counter)
	
	def __str__(self):
		return self.__unicode__().encode('ascii')
	
	def __unicode__(self):
		return "{self.time:08x}{self.machine:06x}{self.process:04x}{self.counter:06x}".format(self=self)
	
	def __repr__(self):
		return "{self.__class__.__name__}('{self}')".format(self=self)
	
	if py3:
		__bytes__ = __str__
		__str__ = __unicode__


class SignedSessionIdentifier(SessionIdentifier):
	__slots__ = ('__secret', '__signature', 'expires')
	def __init__(self, value=None, secret=None, expires=None):
		self.__secret = secret.encode('ascii') if hasattr(secret, 'encode') else secret
		self.__signature = None
		self.expires = expires
		
		super(SignedSessionIdentifier, self).__init__(value)
	
	def parse(self, value):
		if len(value) != 88:
			raise SignatureError("Invalid signed identifier length.")
		
		super(SignedSessionIdentifier, self).parse(value)
		
		self.__signature = value[24:].encode('ascii')
		
		if not self.valid:
			raise SignatureError("Invalid signed identifier.")
	
	@property
	def signed(self):
		return bytes(self) + self.signature
	
	@property
	def signature(self):
		if not self.__signature:
			self.__signature = hmac(
					self.__secret,
					unhexlify(bytes(self)),
					sha256
				).hexdigest()
			
			if hasattr(self.__signature, 'encode'):
				self.__signature = self.__signature.encode('ascii')
		
		return self.__signature
	
	@property
	def valid(self):
		if not self.__signature:
			raise SignatureError("No signature present.")
			return False
		
		if self.expires and (time() - self.time) > self.expires:
			raise SignatureError("Expired signature.")
			return False
		
		challenge = hmac(
				self.__secret,
				unhexlify(bytes(self)),
				sha256
			).hexdigest()
		
		if hasattr(challenge, 'encode'):
			challenge = challenge.encode('ascii')
		
		result = compare_digest(challenge, self.signature)
		
		if not result:
			raise SignatureError("Invalid signature:", repr(challenge), repr(self.signature))
			return False
		
		return True

