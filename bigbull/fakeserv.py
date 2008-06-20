import re
import os
import sys
import glob
import yappy.parser

lv2 = "http://lv2plug.in/ns/lv2core#"
lv2evt = "http://lv2plug.in/ns/ext/event#"
rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
rdfs = "http://www.w3.org/2000/01/rdf-schema#"
rdf_type = rdf + "type"

class DumpRDFModel:
    def addTriple(self, s, p, o):
        print "%s [%s] %s" % (s, p, repr(o))

class SimpleRDFModel:
    def __init__(self):
        self.bySubject = {}
        self.byPredicate = {}
    def getByType(self, classname):
        classes = self.bySubject["$classes"]
        if classname in classes:
            return classes[classname]
        return []
    def getByPropType(self, propname):
        if propname in self.byPredicate:
            return self.byPredicate[propname]
        return []
    def getProperty(self, subject, props, optional = False, single = False):
        if type(props) is list:
            prop = props[0]
        else:
            prop = props
        if type(subject) is str:
            subject = self.bySubject[subject]
        elif type(subject) is dict:
            pass
        else:
            if single:
                return None
            else:
                return []
        anyprops = set()
        if prop in subject:
            for o in subject[prop]:
                anyprops.add(o)
        if type(props) is list:
            if len(props) > 1:
                result = set()
                for v in anyprops:
                    if single:
                        value = self.getProperty(v, props[1:], optional = optional, single = True)
                        if value != None:
                            return value
                    else:
                        result |= set(self.getProperty(v, props[1:], optional = optional, single = False))
                if single:
                    return None
                else:
                    return list(result)
        if single:
            if len(anyprops) > 0:
                if len(anyprops) > 1:
                    raise Exception, "More than one value of " + prop
                return list(anyprops)[0]
            else:
                return None
        return list(anyprops)
        
                
    def addTriple(self, s, p, o):
        if p == rdf_type:
            p = "a"
        if s not in self.bySubject:
            self.bySubject[s] = {}
        if p not in self.bySubject[s]:
            self.bySubject[s][p] = []
        self.bySubject[s][p].append(o)
        if p not in self.byPredicate:
            self.byPredicate[p] = {}
        if s not in self.byPredicate[p]:
            self.byPredicate[p][s] = []
        self.byPredicate[p][s].append(o)
        if p == "a":
            self.addTriple("$classes", o, s)
    def copyFrom(self, src):
        for s in src.bySubject:
            po = src.bySubject[s]
            for p in po:
                for o in po[p]:
                    self.addTriple(s, p, o)
    def dump(self):
        for s in self.bySubject.keys():
            for p in self.bySubject[s].keys():
                print "%s %s %s" % (s, p, self.bySubject[s][p])

def parseTTL(uri, content, model):
    # Missing stuff: translated literals, blank nodes
    print "Parsing: %s" % uri
    prefixes = {}
    lexer = yappy.parser.Lexer([
        (r"(?m)^\s*#[^\n]*", ""),
        ('"""(\n|\r|.)*?"""', lambda x : ("string", x[3:-3])),
        (r'"([^"\\]|\\.)+"', lambda x : ("string", x[1:-1])),
        (r"<>", lambda x : ("URI", uri)),
        (r"<[^>]*>", lambda x : ("URI", x[1:-1])),
        ("[-a-zA-Z0-9_]*:[-a-zA-Z0-9_]*", lambda x : ("prnot", x)),
        ("@prefix", lambda x : ("prefix", x)),
        (r"-?[0-9]+\.[0-9]+", lambda x : ("number", float(x))),
        (r"-?[0-9]+", lambda x : ("number", int(x))),
        ("[a-zA-Z0-9_]+", lambda x : ("symbol", x)),
        (r"[()\[\];.,]", lambda x : (x, x)),
        ("\s+", ""),
    ])
    spo_stack = []
    spo = ["", "", ""]
    item = 0
    anoncnt = 1
    for x in lexer.scan(content):
        if x[0] == '':
            continue
        if x[0] == 'prefix':
            spo[0] = "@prefix"
            item = 1
            continue
        elif (x[0] == '.' and spo_stack == []) or x[0] == ';' or x[0] == ',':
            if item == 3:
                if spo[0] == "@prefix":
                    prefixes[spo[1][:-1]] = spo[2]
                else:
                    model.addTriple(spo[0], spo[1], spo[2])
                if x[0] == '.': item = 0
                elif x[0] == ';': item = 1
                elif x[0] == ',': item = 2
            else:
                raise Exception, uri+": Unexpected " + x[0]
        elif x[0] == "prnot" and item < 3:
            prnot = x[1].split(":")
            if item != 0 and spo[0] == "@prefix":
                spo[item] = x[1]
            else:
                spo[item] = prefixes[prnot[0]] + prnot[1]
            item += 1
        elif (x[0] == 'URI' or x[0] == "string" or x[0] == "number" or (x[0] == "symbol" and x[1] == "a" and item == 1)) and (item < 3):
            if x[0] == "URI" and x[1].find(":") == -1 and x[1][0] != "/":
                # This is quite silly
                x = ("URI", os.path.dirname(uri) + "/" + x[1])
            spo[item] = x[1]
            item += 1
        elif x[0] == '[':
            if item != 2:
                raise Exception, "Incorrect use of ["
            uri2 = uri + "$anon$" + str(anoncnt)
            spo[2] = uri2
            spo_stack.append(spo)
            spo = [uri2, "", ""]
            item = 1
            anoncnt += 1
        elif x[0] == ']' or x[0] == ')':
            if item == 3:
                model.addTriple(spo[0], spo[1], spo[2])
                item = 0
            spo = spo_stack[-1]
            spo_stack = spo_stack[:-1]
            item = 3
        elif x[0] == '(':
            if item != 2:
                raise Exception, "Incorrect use of ("
            uri2 = uri + "$anon$" + str(anoncnt)
            spo[2] = uri2
            spo_stack.append(spo)
            spo = [uri2, "", ""]
            item = 2
            anoncnt += 1
        else:
            print uri + ": Unexpected: " + repr(x)

class FakeServer(object):
    def __init__(self):
        pass

def start():
    global instance
    instance = FakeServer()

def queue(cmdObject):
    global instance
    #try:
    cmdObject.calledOnOK(type(instance).__dict__[cmdObject.type](instance, *cmdObject.args))
    #except:
    #    cmdObject.calledOnError(repr(sys.exc_info()))
    
