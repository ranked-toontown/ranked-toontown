from direct.gui.DirectGui import *
from panda3d.core import *
from toontown.toonbase import TTLocalizer
from toontown.toontowngui import TTDialog
from toontown.shtiker.ShtikerPage import ShtikerPage
from toontown.toonbase import ToontownGlobals
from direct.directnotify import DirectNotifyGlobal


class NametagPage(ShtikerPage):
    """Page for customizing nametag fonts"""
    
    notify = DirectNotifyGlobal.directNotify.newCategory('NametagPage')
    
    def __init__(self):
        ShtikerPage.__init__(self)
        self.nametagStyleButtons = []
        self.currentStyle = 100  # Default to basic
        self.selectedButton = None
        self.gui = None
        self.buttonModels = None
        
    def load(self):
        ShtikerPage.load(self)
        
        # Load GUI models
        self.gui = loader.loadModel('phase_3.5/models/gui/stickerbook_gui')
        self.buttonModels = loader.loadModel('phase_3/models/gui/quit_button')
        
        # Title
        self.title = DirectLabel(
            parent=self,
            relief=None,
            text=TTLocalizer.NametagPageTitle,
            text_scale=0.14,
            pos=(0, 0, 0.6),
            text_fg=(0.05, 0.14, 0.4, 1),
            text_font=ToontownGlobals.getSignFont()
        )
        
        # Instructions
        self.instructions = DirectLabel(
            parent=self,
            relief=None,
            text=TTLocalizer.NametagPageInstructions,
            text_scale=0.05,
            pos=(0, 0, 0.5),
            text_fg=(0.05, 0.14, 0.4, 1),
            text_wordwrap=20,
            text_align=TextNode.ACenter
        )
        
        # Preview frame using quest card background
        self.previewFrame = DirectFrame(
            parent=self,
            relief=None,
            image=self.gui.find('**/questCard'),
            image_scale=(0.6, 0.4, 0.4),
            pos=(0.5, 0, -0.2)
        )
        
        # Preview label
        toonName = localAvatar.getName() if hasattr(localAvatar, 'getName') else "Toon"
        self.previewLabel = DirectLabel(
            parent=self.previewFrame,
            relief=None,
            text=toonName,
            text_scale=0.05,
            pos=(0, 0, 0),
            text_fg=(0.2, 0.1, 0.7, 1),
            text_shadow=(1, 1, 1, 0.8),
            text_wordwrap=8,
            text_align=TextNode.ACenter
        )
        
        # Font name label
        self.fontNameLabel = DirectLabel(
            parent=self,
            relief=None,
            text="Basic Font",
            text_scale=0.11,
            pos=(0, 0, 0.15),
            text_fg=(0.05, 0.14, 0.4, 1),
            text_align=TextNode.ACenter
        )
        
        # Create font selection buttons
        self.createFontButtons()
        
        # Create control buttons
        self.createControlButtons()
        
        # Get current style
        if hasattr(localAvatar, 'nametagStyle'):
            self.currentStyle = localAvatar.nametagStyle
        
        self.updatePreview()
    
    def createFontButtons(self):
        """Create buttons for each available nametag font using proper Toontown button assets"""
        # Get font names
        fontNames = ['Basic'] + list(TTLocalizer.NametagFontNames)
        
        # Create scrolled list for font buttons
        gui = loader.loadModel('phase_3.5/models/gui/friendslist_gui')
        
        # Create main frame
        self.fontListFrame = DirectFrame(
            parent=self,
            relief=None,
            pos=(-0.4, 0, -0.1),
            scale=(0.7, 0.6, 1.0)
        )
        
        # Create scrolled list
        self.fontScrollList = DirectScrolledList(
            parent=self.fontListFrame,
            relief=None,
            pos=(0, 0, -0.15),
            incButton_image=(gui.find('**/FndsLst_ScrollUp'),
                           gui.find('**/FndsLst_ScrollDN'), 
                           gui.find('**/FndsLst_ScrollUp_Rllvr'),
                           gui.find('**/FndsLst_ScrollUp')),
            incButton_relief=None,
            incButton_scale=(0.6, 0.6, -2),
            incButton_pos=(0.42, 0, -0.12),
            incButton_image3_color=Vec4(1, 1, 1, 0.2),
            decButton_image=(gui.find('**/FndsLst_ScrollUp'),
                           gui.find('**/FndsLst_ScrollDN'),
                           gui.find('**/FndsLst_ScrollUp_Rllvr'), 
                           gui.find('**/FndsLst_ScrollUp')),
            decButton_relief=None,
            decButton_scale=(0.6, 0.6, 2),
            decButton_pos=(0.42, 0, 0.22),
            decButton_image3_color=Vec4(1, 1, 1, 0.2),
            itemFrame_pos=(-0.35, 0, 0.22),
            itemFrame_scale=1.0,
            itemFrame_relief=DGG.SUNKEN,
            itemFrame_frameSize=(-0.05, 0.67, -0.4, 0.05),
            itemFrame_frameColor=(0.85, 0.95, 1, 1),
            itemFrame_borderWidth=(0.01, 0.01),
            numItemsVisible=6,
            items=[]
        )
        
        # Create buttons for each font
        for i, fontName in enumerate(fontNames):
            # Determine style index
            if i == 0:
                styleIndex = 100  # Basic style
            else:
                styleIndex = i - 1  # Font index (0-based)
            
            # Create button using proper Toontown button assets
            button = DirectButton(
                relief=None,
                image=(self.buttonModels.find('**/QuitBtn_UP'),
                       self.buttonModels.find('**/QuitBtn_DN'),
                       self.buttonModels.find('**/QuitBtn_RLVR')),
                image_scale=(1.0, 0.6, 0.6),
                image_pos=(0.315, 0, 0),
                text=fontName,
                text_scale=0.05,
                text_pos=(0.315, -0.015),
                text_fg=(0.05, 0.14, 0.4, 1),
                text_shadow=(1, 1, 1, 0.8),
                command=self.selectNametagStyle,
                extraArgs=[styleIndex]
            )
            
            self.nametagStyleButtons.append(button)
            self.fontScrollList.addItem(button)
        
        gui.removeNode()
        
        # Select the current style
        self.selectNametagStyle(self.currentStyle)
    
    def createControlButtons(self):
        """Create Apply and Reset buttons using proper Toontown button assets"""
        # Apply button
        self.applyButton = DirectButton(
            parent=self,
            relief=None,
            image=(self.buttonModels.find('**/QuitBtn_UP'),
                   self.buttonModels.find('**/QuitBtn_DN'),
                   self.buttonModels.find('**/QuitBtn_RLVR')),
            image_scale=(0.8, 1.0, 0.8),
            text=TTLocalizer.NametagPageApply,
            text_scale=0.05,
            text_pos=(0, -0.02),
            text_fg=(0.05, 0.14, 0.4, 1),
            text_shadow=(1, 1, 1, 0.8),
            pos=(0.3, 0, -0.6),
            command=self.applyNametagStyle
        )
        
        # Reset button
        self.resetButton = DirectButton(
            parent=self,
            relief=None,
            image=(self.buttonModels.find('**/QuitBtn_UP'),
                   self.buttonModels.find('**/QuitBtn_DN'),
                   self.buttonModels.find('**/QuitBtn_RLVR')),
            image_scale=(0.8, 1.0, 0.8),
            text=TTLocalizer.NametagPageReset,
            text_scale=0.05,
            text_pos=(0, -0.02),
            text_fg=(0.05, 0.14, 0.4, 1),
            text_shadow=(1, 1, 1, 0.8),
            pos=(-0.3, 0, -0.6),
            command=self.resetNametagStyle
        )
    
    def selectNametagStyle(self, styleIndex):
        """Select a nametag style"""
        self.currentStyle = styleIndex
        self.updatePreview()
        
        # Update button states
        for i, button in enumerate(self.nametagStyleButtons):
            # Determine if this button should be selected
            shouldSelect = False
            if i == 0 and styleIndex == 100:
                shouldSelect = True  # Basic style button
            elif i > 0 and styleIndex == i - 1:
                shouldSelect = True  # Font style button
            
            if shouldSelect:
                button['image_color'] = (0.5, 0.9, 1.0, 1.0)
                self.selectedButton = button
            else:
                button['image_color'] = (1.0, 1.0, 1.0, 1.0)
    
    def updatePreview(self):
        """Update the preview of the selected nametag style"""
        # Get the current toon's name for preview
        toonName = localAvatar.getName() if hasattr(localAvatar, 'getName') else "Toon"
            
        # Determine font based on style
        if self.currentStyle == 100:
            # Basic style uses default font
            previewFont = ToontownGlobals.getInterfaceFont()
            fontText = "Basic Font"
        else:
            # Use the selected font
            if self.currentStyle < len(TTLocalizer.NametagFonts):
                fontPath = TTLocalizer.NametagFonts[self.currentStyle]
                try:
                    previewFont = loader.loadFont(fontPath)
                    if not previewFont:
                        previewFont = ToontownGlobals.getInterfaceFont()
                        fontText = "Font Error"
                    else:
                        fontText = TTLocalizer.NametagFontNames[self.currentStyle]
                except:
                    previewFont = ToontownGlobals.getInterfaceFont()
                    fontText = "Font Error"
            else:
                previewFont = ToontownGlobals.getInterfaceFont()
                fontText = "Unknown Font"
        
        # Update preview label
        self.previewLabel['text'] = toonName
        self.previewLabel['text_font'] = previewFont
        
        # Update font name label
        self.fontNameLabel['text'] = fontText
    
    def applyNametagStyle(self):
        """Apply the selected nametag style"""
        # Send request to server using the proper pattern
        localAvatar.d_requestNametagStyle(self.currentStyle)
        self.showConfirmation(TTLocalizer.NametagPageApplied)
    
    def resetNametagStyle(self):
        """Reset to default nametag style"""
        self.selectNametagStyle(100)  # Reset to basic style
        localAvatar.d_requestNametagStyle(100)
        self.showConfirmation(TTLocalizer.NametagPageReset)
    
    def showConfirmation(self, message):
        """Show confirmation dialog"""
        if hasattr(self, 'confirmDialog') and self.confirmDialog:
            self.confirmDialog.cleanup()
        
        self.confirmDialog = TTDialog.TTGlobalDialog(
            message=message,
            doneEvent='nametagConfirmAck',
            style=TTDialog.Acknowledge
        )
        self.accept('nametagConfirmAck', self.__handleConfirmAck)
        self.confirmDialog.show()
    
    def __handleConfirmAck(self):
        """Handle confirmation dialog acknowledgment"""
        self.ignore('nametagConfirmAck')
        if hasattr(self, 'confirmDialog') and self.confirmDialog:
            self.confirmDialog.cleanup()
            self.confirmDialog = None
    
    def enter(self):
        ShtikerPage.enter(self)
        # Update current style when entering the page
        if hasattr(localAvatar, 'nametagStyle'):
            self.selectNametagStyle(localAvatar.nametagStyle)
    
    def exit(self):
        ShtikerPage.exit(self)
        # Clean up any open dialogs
        if hasattr(self, 'confirmDialog') and self.confirmDialog:
            self.confirmDialog.cleanup()
            self.confirmDialog = None
    
    def unload(self):
        """Cleanup when page is unloaded"""
        if hasattr(self, 'confirmDialog') and self.confirmDialog:
            self.confirmDialog.cleanup()
            self.confirmDialog = None
        
        # Clean up GUI models
        if self.gui:
            self.gui.removeNode()
            self.gui = None
        if self.buttonModels:
            self.buttonModels.removeNode()
            self.buttonModels = None
            
        ShtikerPage.unload(self) 