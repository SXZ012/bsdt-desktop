const {app,BrowserWindow,dialog}=require('electron');
const path=require('node:path');
let mainWindow=null,windowReady=false;
function open(){
 const win=new BrowserWindow({width:1440,height:960,minWidth:900,minHeight:650,show:false,icon:path.join(__dirname,'../build-assets/bsdt.ico'),backgroundColor:'#e8edf5',autoHideMenuBar:true,webPreferences:{contextIsolation:true,nodeIntegration:false,sandbox:true}});
 mainWindow=win;windowReady=false;
 // First paint includes the static startup screen or the research workspace.
 // Showing the window does not wait for any network request.
 win.once('ready-to-show',()=>{if(!win.isDestroyed()){windowReady=true;win.show()}});
 win.on('closed',()=>{if(mainWindow===win){mainWindow=null;windowReady=false}});
 win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
 win.webContents.on('will-navigate',(event,url)=>{if(!url.startsWith('file:'))event.preventDefault()});
 win.loadFile(path.join(__dirname,'../dist/index.html')).catch(()=>{
  dialog.showErrorBox('BSDT 启动失败','无法加载工作台界面，请重新安装桌面客户端。');
  if(!win.isDestroyed())win.destroy();
 });
}
app.setAppUserModelId('com.bsdt.internal');
if(!app.requestSingleInstanceLock())app.quit();
else{
 app.on('second-instance',()=>{if(mainWindow&&windowReady&&!mainWindow.isDestroyed()){if(mainWindow.isMinimized())mainWindow.restore();mainWindow.show();mainWindow.focus()}});
 app.whenReady().then(()=>{open();app.on('activate',()=>{if(!BrowserWindow.getAllWindows().length)open()})});
 app.on('window-all-closed',()=>{if(process.platform!=='darwin')app.quit()});
}