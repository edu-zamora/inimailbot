from google.appengine.ext import webapp
register = webapp.template.create_template_register()

def gt(a, b):
	return a > b

def lt(a, b):
	return a < b

def gte(a, b):
	return a >= b

def lte(a, b):
	return a <= b

def sub(a, b):
	return int(a) - int(b)

def mul(a, b):
	return int(a) * int(b)

def div(a, b):
	return int(a) / int(b)

def divtrunc(a, b):
	return int(a) // int(b)

def mod(a, b):
	return int(a) % int(b)

def maxof(a, b):
	if a >= b:
		return a
	else:
		return b

def minof(a, b):
	if a <= b:
		return a
	else:
		return b

register.filter(gt)
register.filter(lt)
register.filter(gte)
register.filter(lte)
register.filter(sub)
register.filter(mul)
register.filter(div)
register.filter(divtrunc)
register.filter(mod)
register.filter(maxof)
register.filter(minof)

