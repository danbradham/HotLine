'''
HotLine
Dan Bradham
danielbradham@gmail.com
http://danbradham.com

A convenient popup script editor.
Up and down keys shuffle through HotLine History.
Tab key changes mode.

Set a hotkey to the following python script:

import maya.cmds as cmds
try:
    hl.enter()
except:
    from hotline import HotLine
    hl = HotLine()
    hl.enter()
'''

import re
import inspect
try:
    import sip
    wrapinstance = sip.wrapinstance
    try:
        sip.setapi('QVariant', 2)
        sip.setapi('QString', 2)
    except:
        pass
    from PyQt4 import QtGui, QtCore
except ImportError:
    import shiboken
    wrapinstance = shiboken.wrapInstance
    from PySide import QtGui, QtCore
except ImportError:
    raise ImportError("PyQt and PySide modules cannot be found.")
import maya.OpenMayaUI as OpenMayaUI
import maya.cmds as cmds
import maya.mel as mel


def getMayaWindow():
    #Get the maya main window as a QMainWindow instance
    ptr = OpenMayaUI.MQtUtil.mainWindow()
    return wrapinstance(long(ptr), QtCore.QObject)


def format_text(r, g, b, a=255, style=''):
    color = QtGui.QColor(r, g, b, a)
    fmt = QtGui.QTextCharFormat()
    fmt.setForeground(color)
    if "bold" in style:
        fmt.setFontWeight(QtGui.QFont.Bold)
    if "italic" in style:
        fmt.setFontItalic(True)
    return fmt

HISTYLES = {
    'keywords': format_text(246, 38, 114),
    'operators': format_text(246, 38, 114),
    'delimiters': format_text(255, 255, 255),
    'defclass': format_text(102, 217, 239),
    'string': format_text(230, 219, 116),
    'comment': format_text(117, 113, 94),
    'numbers': format_text(132, 129, 255),}

PY = {
"keywords":
    ["and", "assert", "break", "class", "continue", "def",
    "del", "elif", "else", "except", "exec", "finally",
    "for", "from", "global", "if", "import", "in",
    "is", "lambda", "not", "or", "pass", "print",
    "raise", "return", "try", "while", "yield"],
"operators":
    ["\+", "-", "\*", "\*\*", "/", "//", "\%", "<<", ">>", "\&", "\|", "\^",
    "~", "<", ">", "<=", ">=", "==", "!=", "<>", "=", "\+=", "-=",
    "\*=", "/=", "//=", "\%=", "\&=", "|=", "\^=", ">>=", "<<=", "\*\*="],
"delimiters":
    ["\(", "\)", "\[", "\]", "\{", "\}"],}

class PyHighlighter(QtGui.QSyntaxHighlighter):
    '''Python syntax highliter
    '''

    def __init__(self, parent):
        super(PyHighlighter, self).__init__(parent)

        self.multiline_rules = [
            (QtCore.QRegExp("'''"), HISTYLES['string']),
            (QtCore.QRegExp('"""'), HISTYLES['string']),]

        rules = []
        for key, items in PY.iteritems():
            for item in items:
                rules.append((r'%s' % item, 0, HISTYLES[key]))

        rules.extend([
            # Double-quoted string, possibly containing escape sequences
            (r'"[^"\\]*(\\.[^"\\]*)*"', HISTYLES['string']),
            # Single-quoted string, possibly containing escape sequences
            (r"'[^'\\]*(\\.[^'\\]*)*'", HISTYLES['string']),
            # 'def' followed by an identifier
            (r'\bdef\b\s*(\w+)', HISTYLES['defclass']),
            # 'class' followed by an identifier
            (r'\bclass\b\s*(\w+)', HISTYLES['defclass']),
            # From '#' until a newline
            (r'#[^\n]*', HISTYLES['comment']),
            # Numeric literals
            (r'\b[+-]?[0-9]+[lL]?\b', HISTYLES['numbers']),
            (r'\b[+-]?0[xX][0-9A-Fa-f]+[lL]?\b', HISTYLES['numbers']),
            (r'\b[+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\b', HISTYLES['numbers']),])

        self.rules = [(QtCore.QRegExp(pat), fmt) for pat, fmt in rules]

    def highlightBlock(self, text):
        """Apply syntax highlighting to the given block of text."""

        for expression, format in self.rules:
            index = expression.indexIn(text, 0)

            while index >= 0:
                index = expression.pos()
                length = expression.matchedLength()
                self.setFormat(index, length, format)
                index = expression.indexIn(text, index + length)
        
        self.setCurrentBlockState(0)
        
        #multi-line strings

        last_state = self.previousBlockState()
        if last_state not in (1, 2):
            for i, rule in enumerate(self.multiline_rules):
                expression = rule[0]
                start_index = expression.indexIn(text, 0)
                if start_index != -1:
                    break
        else:
            start_index = 0
            start_length = 3 if last_state not in (1, 2) else 0
            expression = self.multiline_rules[last_state - 1]
        while start_index >= 0:
            end_index = expression.indexIn(text, start_index + 3)

            if end_index == -1:
                self.setCurrentBlockState(1)
                comment_length = text.length() - start_index
            else:
                comment_length = end_index - start_index + 3
            self.setFormat(start_index, comment_length, format)
            start_index = expression.indexIn(text, comment_length)

class HotField(QtGui.QTextEdit):
    '''QTextEdit with history and dropdown completion.'''

    def __init__(self, parent=None):
        super(HotField, self).__init__(parent)
        self.history = []
        self.history_index = 0
        self.mel_callables = [name for name, data in inspect.getmembers(cmds, callable)]
        self.py_callables = ['cmds.' + name for name in self.mel_callables]

        #Dropdown Completer
        self.completer_list = QtGui.QStringListModel(self.py_callables)
        self.completer = QtGui.QCompleter(self.completer_list, self)
        self.completer.setCompletionMode(QtGui.QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.completer.activated.connect(self.insertCompletion)

        #Highlighter
        self.highlighter = PyHighlighter(self)

    def setup_completer(self, mode):
        '''Change completer word list.'''

        completion_list = {
        "PY": self.py_callables,
        "MEL": self.mel_callables,
        "SEL": cmds.ls(),
        "REN": [],
        "NODE": cmds.allNodeTypes()}[mode]
        self.completer_list.setStringList(completion_list)

    def insertCompletion(self, completion):
        tc = self.textCursor()
        tc.movePosition(QtGui.QTextCursor.Left)
        tc.movePosition(QtGui.QTextCursor.EndOfWord)
        tc.insertText(completion[len(self.completer.completionPrefix()):])
        self.setTextCursor(tc)

    def textUnderCursor(self):
        tc = self.textCursor()
        tc.select(QtGui.QTextCursor.WordUnderCursor)
        return tc.selectedText()

    def focusInEvent(self, event):
        if self.completer:
            self.completer.setWidget(self);
        QtGui.QTextEdit.focusInEvent(self, event)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Tab and not self.completer.popup().isVisible():
            self.parent().setMode()
            return
        elif event.key() == QtCore.Qt.Key_Up:
            if self.history_index:
                self.history_index -= 1
                if self.text() and not self.text() in self.history:
                    self.history.append(self.text())
                self.setText(self.history[self.history_index])
        elif event.key() == QtCore.Qt.Key_Down:
            self.history_index += 1
            if self.history_index < len(self.history):
                self.setText(self.history[self.history_index])
            elif self.history_index == len(self.history):
                self.clear()
        else:
            if self.completer.popup().isVisible():
                if event.key() in (
                QtCore.Qt.Key_Enter,
                QtCore.Qt.Key_Return,
                QtCore.Qt.Key_Escape,
                QtCore.Qt.Key_Tab,
                QtCore.Qt.Key_Backtab):
                    event.ignore()
                    return

            ## has ctrl-E been pressed??
            isShortcut = (event.modifiers() == QtCore.Qt.ControlModifier and
                          event.key() == QtCore.Qt.Key_E)
            if (not self.completer or not isShortcut):
                QtGui.QTextEdit.keyPressEvent(self, event)

            ## ctrl or shift key on it's own??
            ctrlOrShift = event.modifiers() in (QtCore.Qt.ControlModifier ,
                    QtCore.Qt.ShiftModifier)
            if ctrlOrShift and not event.text():
                # ctrl or shift key on it's own
                return

            eow = "~!@#$%^&*()_+{}|:\"<>?,/;'[]\\-=" #end of word

            hasModifier = ((event.modifiers() != QtCore.Qt.NoModifier) and
                            not ctrlOrShift)

            completionPrefix = self.textUnderCursor()

            if (not isShortcut and (hasModifier or not event.text() or
            len(completionPrefix) < 3)):
                self.completer.popup().hide()
                return

            if (completionPrefix != self.completer.completionPrefix()):
                self.completer.setCompletionPrefix(completionPrefix)
                popup = self.completer.popup()
                popup.setCurrentIndex(
                    self.completer.completionModel().index(0,0))

            cr = self.cursorRect()
            cr.setWidth(self.completer.popup().sizeHintForColumn(0)
                + self.completer.popup().verticalScrollBar().sizeHint().width())
            self.completer.complete(cr) ## popup it up!


class HotLine(QtGui.QDialog):
    '''A popup dialog with a single QLineEdit(HotField) and several modes of input.'''

    style = '''QPushButton {
                    border:0;
                    background: none;}
                QPushButton:pressed {
                    border:0;
                    color: rgb(0, 35, 55)}
                QLineEdit {
                    background-color: none;
                    border: 0;
                    border-bottom: 1px solid rgb(42, 42, 42);
                    padding-left: 10px;
                    padding-right: 10px;
                    height: 20;}
                QLineEdit:focus {
                    outline: none;
                    background: none;
                    border: 0;
                    height: 20;}'''

    modes = ['PY', 'MEL', 'SEL', 'REN', 'NODE']

    def __init__(self, parent=getMayaWindow()):
        super(HotLine, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Popup|QtCore.Qt.FramelessWindowHint|QtCore.Qt.WindowStaysOnTopHint)
        self.resize(400, 24)
        self.setObjectName('HotLine')
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.mode = 0

        self.hotfield = HotField()
        #self.hotfield.returnPressed.connect(self.eval_hotfield)
        self.mode_button = QtGui.QPushButton('PY')
        self.mode_button.clicked.connect(self.setMode)
        self.mode_button.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)
        self.mode_button.setFixedWidth(50)
        self.layout = QtGui.QGridLayout()
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(0)
        self.layout.addWidget(self.hotfield, 0, 1)
        self.layout.addWidget(self.mode_button, 0, 0)
        self.setLayout(self.layout)

        self.setStyleSheet(self.style)

    def setMode(self):
        if self.mode == len(self.modes) - 1:
            self.mode = 0
        else:
            self.mode += 1

        #set hotfield completer
        self.hotfield.setup_completer(self.modes[self.mode])
        self.mode_button.setText(self.modes[self.mode])
        self.hotfield.setFocus()

    def eval_hotfield(self):
        input_str = str(self.hotfield.text())
        self.hotfield.history.append(input_str)
        self.hotfield.history_index = len(self.hotfield.history)
        if self.mode == 0:
            cmds.evalDeferred(input_str)
            cmds.repeatLast(addCommand='python("{0}")'.format(input_str))
        elif self.mode == 1:
            mel.eval(input_str)
            cmds.repeatLast(addCommand=input_str)
        elif self.mode == 2:
            cmds.select(input_str, replace=True)
        elif self.mode == 3:
            self.rename(str(input_str))
        elif self.mode == 4:
            self.create_node(input_str)
        self.exit()

    def create_node(self, input_str):
        input_buffer = input_str.split()
        if len(input_buffer) > 1:
            node_type, node_name = input_buffer
        else:
            node_type = input_buffer[0]
            node_name = None

        node_class = cmds.getClassification(node_type)

        #Wrap node creation and naming in a single chunk
        cmds.undoInfo(openChunk=True)

        if node_class:
            if "utility" in node_class[0].lower():
                node = cmds.shadingNode(node_type, asUtility=True)
            elif "shader" in node_class[0].lower():
                node = cmds.shadingNode(node_type, asShader=True)
            elif "texture" in node_class[0].lower():
                node = cmds.shadingNode(node_type, asTexture=True)
            elif "rendering" in node_class[0].lower():
                node = cmds.shadingNode(node_type, asRendering=True)
            elif "postprocess" in node_class[0].lower():
                node = cmds.shadingNode(node_type, asPostProcess=True)
            elif "light" in node_class[0].lower():
                node = cmds.shadingNode(node_type, asLight=True)
            else:
                node = cmds.createNode(node_type)
        else:
            node = cmds.createNode(node_type)

        if node_name:
            cmds.rename(node, node_name.replace('\"', ''))

        cmds.undoInfo(closeChunk=True)

    def rename(self, r_string):
            '''string processing'''
            nodes = cmds.ls(sl=True, long=True)
            rename_strings = r_string.split()

            cmds.undoInfo(openChunk=True)

            for rename_string in rename_strings:
                remMatch = re.search('\-', rename_string)
                addMatch = re.search('\+', rename_string)
                seq_length = rename_string.count('#')

                #Handle subtract tokens
                if remMatch:
                    rename_string = rename_string.replace('-', '')
                    for node in nodes:
                        node_shortname = node.split('|')[-1]
                        newName = node_shortname.replace(rename_string, '')
                        node = cmds.rename(node, newName)

                #Handle add tokens
                elif addMatch:
                    for i, node in enumerate(nodes):
                        name = rename_string
                        node_shortname = node.split('|')[-1]
                        if seq_length:
                            seq = str(i+1).zfill(seq_length)
                            name = name.replace('#' * seq_length, seq)
                        if name.endswith('+'):
                            node = cmds.rename(node, name.replace('+', '') + node_shortname)
                        elif name.startswith('+'):
                            node = cmds.rename(node, node_shortname + name.replace('+', ''))
                        else:
                            print "+ symbols belong at the front or the end of a string"
                else:

                    #Handle Search Replace
                    if len(rename_strings) == 2:
                        seq_length = rename_strings[-1].count('#')
                        for i, node in enumerate(nodes):
                            node_shortname = node.split('|')[-1]
                            name = rename_strings[-1]
                            if seq_length:
                                seq = str(i+1).zfill(seq_length)
                                name = name.replace('#' * seq_length, seq)
                            node = cmds.rename(node, node_shortname.replace(rename_strings[0], name))
                        break

                    #Handle Full Rename
                    elif len(rename_strings) == 1:
                        for i, node in enumerate(nodes):
                            name = rename_string
                            if seq_length:
                                seq = str(i+1).zfill(seq_length)
                                name = name.replace('#' * seq_length, seq)
                            cmds.rename(node, name)

            cmds.undoInfo(closeChunk=True)

    def enter(self):
        pos = QtGui.QCursor.pos()
        self.move(pos.x(), pos.y())
        self.show()
        self.hotfield.setFocus()

    def exit(self):
        self.hotfield.clear()
        self.close()


if __name__ == '__main__':
    hl = HotLine()
    hl.enter()
