import xml.etree.ElementTree as et


class Helper:
    # Working on XML file
    # -Build, Read, Write
    
    def __init__(self, path):
        self.path = path
        
    def init(self, tag):
        # build a new xml file with single empty tag
        root = et.Element(tag)
        tree = et.ElementTree(root)
        self.tree = tree
        self.update()
        
    def update(self):
        # overwrite a xml file with existing tree elements
        self.tree.write(self.path)
        
    def handle(self):
        # get the main tree element of a xml file
        self.tree = et.parse(self.path)
        root = self.tree.getroot()
        return root
    
    def write(self, xpath, tag=None, val=None, attrib=None):
        # write new sub-element on a xml file
        # with specific location
        # with optional creating new tag
        # with optional adding value and/or list of attributes
        tree = self.handle().find(xpath)
        if tag is not None:
            tree = et.SubElement(tree, tag)
        if val is not None:
            # value of element if provided
            tree.text = val
        if attrib is not None:
            # list of attribute if provided
            for key in attrib:
                tree.attrib[key] = attrib[key]
            
        self.update()
    
    def read(self, xpath):
        # read value of a specific sub-element
        return self.handle().find(xpath).text
    
    def exist(self, xpath):
        return self.handle().find(xpath) is not None
        
    def tostring(self):
        # help to print out the whole xml file for examination
        tree = self.handle()
        et.indent(tree)
        txt = et.tostring(tree, encoding='utf8').decode('utf8')
        return txt
    

if __name__ == '__main__':
    PATH = './Test_XML.xml'
    xml = Helper(PATH)
    
    print(f">> Created new XML file at {PATH}")
    xml.init('data')
    xml.write(xpath='.', tag='test', attrib={'type': 'testing xml', 'date': 'today'})
    xml.write(xpath='./test', tag='subj', attrib={'id': 'current location'})
    xml.write(xpath='./test/subj', tag='path', val='error')
    
    xml.read(xpath='./test/subj/path')
    print("\n>> Original XML\n")
    print(xml.tostring())
    
    xml.write(xpath="./test[@date='today']/subj[@id='current location']/path", val=PATH)
    print("\n>> Modified XML\n")
    print(xml.tostring())
    