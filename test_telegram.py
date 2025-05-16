from telegram.ext import Application,CommandHandler, ContextTypes,MessageHandler,filters,CallbackQueryHandler
from telegram import Update,InlineKeyboardButton,InlineKeyboardMarkup
import os
import PyPDF2
from pdf2image import convert_from_path
import logging
from datetime import datetime
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from pytesseract import image_to_string
import json
import asyncio
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
Bot_token=os.getenv('BOT_TOKEN')
drive_folder_id = os.getenv('DRIVE_FOLDER_ID')
# service_account_file='service-account-key.json'
invoice_folder=os.getenv('INVOICE_FOLDER_NAME')
invoice_file=os.getenv('INVOICE_FILE_NAME')
columns=['sender','buyer','invoice_no','date','total_amount','filename','inserted_by']

api_key=os.getenv('GOOGLE_API_KEY')
genai.configure(api_key=api_key)
modal=genai.GenerativeModel("gemini-1.5-flash")
google_file_info = {
    "type": os.getenv("GOOGLE_TYPE"),
    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GOOGLE_PRIVATE_KEY"),
    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
    "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
    "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_X509_CERT_URL"),
    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL"),
    "universe_domain": os.getenv("GOOGLE_UNIVERSE_DOMAIN")
}
SCOPES = ['https://www.googleapis.com/auth/drive','https://www.googleapis.com/auth/spreadsheets']
credentials= service_account.Credentials.from_service_account_info(google_file_info,scopes=SCOPES)
service= build('drive','v3',credentials=credentials)
sheet_service=build('sheets','v4',credentials=credentials)

def check_if_file_exists(service,drive_folder_id,file_name):
    query=f"name='{file_name}' and '{drive_folder_id}' in parents and trashed=false"
    results= service.files().list(q=query,spaces='drive',fields='files(id,name)').execute()
    items= results.get('files',[])
    if items:
        return items[0]['id']
    else:
        return None

def get_or_create_folder(drive_service,folder_name,parent_id=None):
    query=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    query += f" and trashed=false"
    response= drive_service.files().list(
        q=query,
        spaces='drive',
        fields='files(id,name)',
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    folders= response.get('files',[])
    if folders:
        return folders[0]['id']
    
    folder_metadata= {
        'name':folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        folder_metadata['parents']=[parent_id]
    folder= drive_service.files().create(
        body= folder_metadata,
        fields= 'id',
        supportsAllDrives=True
    ).execute()
    folder_id= folder.get('id')
    return folder_id

def get_or_create_sheet(drive_service, sheet_service, spreadsheet_name,folder_id,columns):
    
    query = f"name='{spreadsheet_name}' and mimeType='application/vnd.google-apps.spreadsheet'"
    query += f" and '{folder_id}' in parents and trashed=false"

    response= drive_service.files().list(
        q=query,
        spaces='drive',
        fields='files(id, name)'
    ).execute()
    spreadsheets= response.get('files',[])
    if spreadsheets:
        spreadsheet_id= spreadsheets[0]['id']
        try:
            sheet_metadata= sheet_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets= sheet_metadata.get('sheets','')
            if sheets:
                return spreadsheet_id
        except Exception as e:
            logging.info(str(e))
    spreadsheet_body={
        'properties':{
            'title': spreadsheet_name
        },
        'sheets':[
            {
                'properties':{
                    'title':'Sheet1'
                }
            }
        ]
    }
    try:
        spreadsheet = sheet_service.spreadsheets().create(
            body= spreadsheet_body
        ).execute()
        spreadsheet_id= spreadsheet.get('spreadsheetId')
        
        file= drive_service.files().get(
            fileId= spreadsheet_id,
            fields='parents'
        ).execute()
        previous_parents=",".join(file.get('parents',[]))

        drive_service.files().update(
            fileId= spreadsheet_id,
            addParents=folder_id,
            removeParents= previous_parents,
            fields= 'id, parents'
        ).execute()

        sheet_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range='Sheet1!A1',
            valueInputOption='RAW',
            body={
                'values':[columns]
            }
        ).execute()
        return spreadsheet_id
    except Exception as e:
            logger.error(f"Error creating  spreadsheet: {str(e)}")


async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('This is gift from the legend coder to owner of vee Shores infra \n =>enter "/help" for more info \n =>enter invoice pdf')
  
async def help(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("this is chatbot from best coder ever you seen in your life \n  so here \n => enter whatever text for ai generated response \n =>enter pdf file of invoice for to enter into the specified drive folder \n if the file  already exist in folder than it only updates file \n and if file does not exists than it creates that file in google drive and add it's content according to requirement(it will extract all data from pdf whatever type text or image pdf it extraxts data and fetch it's main content with AI and than store that data  ) to invoices file in summary folder(it created both if not exists)")  

async def common_method(update:Update,context:ContextTypes.DEFAULT_TYPE,data,file_name,user_name,local_file_path):
            response2= modal.generate_content(f"fetch me Who sent it as sender,For who it is for as buyer,Invoiceno.,Date in dd/mm/yyyy format,Total amount in numbers from {data} and give response in list of string so i can access it directly in python and remember no extra text or characters only answer also no any comments and answer only in one line also write 'no val' where any of five not found but list should length of 5 and in order by [sender,buyer,Invoiceno.,Date,Total amount]")
            
            output_data= response2.text
            output_data= output_data.split("[")[1]
            output_data= output_data.split("]")[0]
            output_data=output_data.replace("'","")
                
            final_data=output_data.split(",")
               
            final_data=final_data+[file_name,user_name]
                
            final_data=[item.strip() for item in final_data]
 
            await update.message.reply_text("processing")       
            invoice_folder_id= get_or_create_folder(service,invoice_folder,drive_folder_id)
            await update.message.reply_text("processing")      
            invoice_file_id= get_or_create_sheet(service,sheet_service,invoice_file,invoice_folder_id,columns)
            
            
                
            context.user_data['final_data']=final_data
            context.user_data['invoice_file_id']=invoice_file_id
            context.user_data['sheet_service']=sheet_service
            context.user_data['local_file_path']= local_file_path
            formatted_data = (
                f"📄 Information:\n\n"
                f"sender: {final_data[0]}\n"
                f"buyer: {final_data[1]}\n"
                f"invoice_no: {final_data[2]}\n"
                f"date: {final_data[3]}\n"
                f"total_amount: {final_data[4]}\n"
                f"Filename: {final_data[5]}\n"
                f"Uploaded By: {final_data[6]}\n\n"
                f"Is this information correct now?"
            )
            keyboard=[
                [
                    InlineKeyboardButton("✅ Yes, Confirm",callback_data=json.dumps({"action":"Confirm"})),
                    InlineKeyboardButton("✏️ No, Edit", callback_data=json.dumps({"action":"Edit"})),
                ],
                [InlineKeyboardButton("❌ Cancel",callback_data=json.dumps({"action":"Cancel"}))]
            ]
            await update.message.reply_text(
                f"copy below dataformat if you want to edit \n"
                f"sender: {final_data[0]}\n"
                f"buyer: {final_data[1]}\n"
                f"invoice_no: {final_data[2]}\n"
                f"date: {final_data[3]}\n"
                f"total_amount: {final_data[4]}\n"
            )
            reply_markup=InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(formatted_data,reply_markup=reply_markup)

async def extract_data(update:Update,context:ContextTypes.DEFAULT_TYPE):
    user= update.message.from_user
    user_name= user.first_name
    file= update.message.document
    file_name=f"{file.file_name}"
    new_file= await context.bot.get_file(file.file_id)
    path=f"asdf2/{file.file_name}"
    os.makedirs('asdf2',exist_ok=True)
    
    await new_file.download_to_drive(path)
    try:
        local_file_path= path
        try:
            
            data=''
            with open(path,'rb') as pdf_file:
                    reader = PyPDF2.PdfReader(pdf_file)
                    
                    for page in reader.pages:
                        data+=page.extract_text()
            import gc        
            gc.collect()
            if data=='':
                images=convert_from_path(path, use_pdftocairo=True)
                try:
                    for image in images:
                        try:
                            data+= image_to_string(image)
                        finally:
                            image.close()
                finally:
                    del images
            await common_method(update,context,data,file_name,user_name,local_file_path)

        except Exception as e:
            logger.error(f"Drive upload failed: {str(e)}")
            await update.message.reply_text("❌ Failed to upload to Drive. Please try again later.")
        
        
      
    except Exception as e:
        await update.message.reply_text(f"error : {str(e)}")
        


async def extract_image_data(update:Update,context:ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_name = user.first_name
    file = update.message.document
    file_name = f"{file.file_name}"
    new_file = await context.bot.get_file(file.file_id)
    path = f"asdf2/{file.file_name}"
    os.makedirs('asdf2', exist_ok=True)
    await new_file.download_to_drive(path)
    try:
        local_file_path= path
        try:

            data=''
            
            data+= image_to_string(path)
            await common_method(update,context,data,file_name,user_name,local_file_path)

        except Exception as e:
            logger.error(f"Drive upload failed: {str(e)}")
            await update.message.reply_text("❌ Failed to upload to Drive. Please try again later.")
        
        
        
    except Exception as e:
        await update.message.reply_text(f"error : {str(e)}")

    
async def extract_photo_data(update:Update,context:ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_name = user.first_name
    photo = update.message.photo[-1]  
    file_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg" 
    new_file = await context.bot.get_file(photo.file_id)
    path = f"asdf2/{file_name}"
    os.makedirs('asdf2', exist_ok=True)
    
    await new_file.download_to_drive(path)
    try:
        local_file_path= path
        try:
            data=''
            
            data+= image_to_string(path)
            await common_method(update,context,data,file_name,user_name,local_file_path)

           
        except Exception as e:
            logger.error(f"Drive upload failed: {str(e)}")
            await update.message.reply_text("❌ Failed to upload to Drive. Please try again later.")
        
        
       
    except Exception as e:
        await update.message.reply_text(f"error : {str(e)}")

    
async def handle_edited_data(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_edit',False):
        message_text = update.message.text
        lines= message_text.strip().split("\n")
        
        new_data=context.user_data.get('final_data',[])
        
        for line in lines:
            if ":" in line:
                key,val=line.split(":",1)
                key=key.strip().lower()
                val=val.strip()
                if key == 'sender':
                    new_data[0]=val
                elif key == 'buyer':
                    new_data[1]=val
                elif key == 'invoice_no':
                    new_data[2]=val
                elif key == 'date':
                    new_data[3]=val
                elif key == 'total_amount':
                    new_data[4]=val
        context.user_data['final_data']= new_data
        context.user_data['waiting_for_edit']=False
        
        formatted_data = (
            f"📄 Updated Information:\n\n"
            f"sender: {new_data[0]}\n"
            f"buyer: {new_data[1]}\n"
            f"invoice_no: {new_data[2]}\n"
            f"date: {new_data[3]}\n"
            f"total_amount: {new_data[4]}\n"
            f"Filename: {new_data[5]}\n"
            f"Uploaded By: {new_data[6]}\n\n"
            f"Is this information correct now?"
        )
        
        keyboard=[
            [
                InlineKeyboardButton("✅ Yes, Confirm",callback_data=json.dumps({"action":"Confirm"})),
                InlineKeyboardButton("✏️ No, Edit",callback_data=json.dumps({"action":"Edit"})),
                
            ],
            [InlineKeyboardButton("❌ Cancel",callback_data=json.dumps({"action":"Cancel"}))]
        ]
        reply_markup=InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            formatted_data,
            reply_markup=reply_markup
        )
    else:
        await handle_text(update,context)
                    
async def button_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    query= update.callback_query   
    await query.answer()
    
    data= json.loads(query.data) 
    action= data.get("action")
    final_data= context.user_data.get('final_data',[])
    invoice_file_id= context.user_data.get('invoice_file_id')
    sheet_service= context.user_data.get('sheet_service')
    local_file_path=context.user_data.get('local_file_path')
    if action == "Confirm":
        await query.message.reply_text(f"✅ Data confirmed now performing Drive operation")
        try:
            
            file_name= str(final_data[3])+'_'+str(final_data[0]).replace(' ','_')+'_'+os.path.basename(local_file_path)
            existing_file_id= check_if_file_exists(service,drive_folder_id,file_name)
            update_if_exists=True
            media= None
            try:
                media= MediaFileUpload(local_file_path,resumable=True)
                if existing_file_id and update_if_exists:
                    file= service.files().update(
                        fileId=existing_file_id,
                        media_body= media,
                        fields='id'
                    ).execute()
                    await query.message.reply_text(f"✅ File successfully Updated to Drive. ID: {existing_file_id}")
                   
                elif not existing_file_id:
                   
                    
                    file_metadata={
                        'name':file_name,
                        'parents':[drive_folder_id]
                    }
                    file= service.files().create(body=file_metadata,media_body=media,fields='id').execute()
                    result=sheet_service.spreadsheets().values().append(
                        spreadsheetId=invoice_file_id,
                        range='Sheet1!A1',
                        valueInputOption='USER_ENTERED',
                        insertDataOption='INSERT_ROWS',
                        body={
                            'values':[final_data]
                        }
                                
                    ).execute()
                    await query.message.reply_text(f"✅ File successfully Uploaded to Drive. ID: {file.get('id')}")
                
            finally:
                if media:
                    del media
                import gc
                gc.collect()
            await query.message.reply_text(str(final_data)+ "inserted")  
        except Exception as e:
            await query.message.reply_text(f"❌ File error to append data to invoices google sheet {str(e)}")
            await delete_file_directly(local_file_path,update.effective_chat.id,context.bot)
        finally:
            await query.message.reply_text(f"Attempting to clean up temporary file: {os.path.basename(local_file_path)}...")
            await delete_file_directly(local_file_path,update.effective_chat.id,context.bot)
            context.user_data.pop('final_data',None)
            context.user_data.pop('waiting_for_edit',None)

    elif action=="Edit":
        field_names = ['sender', 'buyer', 'invoice_no', 'date', 'total_amount']
        await query.edit_message_text(
            "Please provide corrected information in this format:\n\n"
            "sender: Company Name\n"
            "buyer: Customer Name\n"
            "invoice_no: INV-12345\n"
            "date: DD/MM/YYYY\n"
            "total_amount: 123.45\n\n"
            "Send this information as a reply."
        )
        context.user_data['waiting_for_edit']=True
        
    elif action=="Cancel":
        await query.edit_message_text("❌ Operation cancelled. Data was not saved.")
        context.user_data['waiting_for_edit']=False
        if local_file_path and os.path.exists(local_file_path): 
             await query.message.reply_text(f"Attempting to clean up temporary file from cancelled operation: {os.path.basename(local_file_path)}...")
             await delete_file_directly(local_file_path, update.effective_chat.id, context.bot)
            

async def handle_text(update:Update,context:ContextTypes.DEFAULT_TYPE):
    message_text= update.message.text

    response=modal.generate_content(message_text)
    response_text= response.text
    await update.message.reply_text(response_text)            
        
async def delete_file_directly(file_path,chat_id,bot,retries=5,initial_delay_seconds=1,backoff_factor=1.5):
    
    
    current_delay=initial_delay_seconds
    for attempt in range(retries):
        try:
            if os.path.exists(file_path):
                await asyncio.sleep(current_delay)
                os.remove(file_path)
                return True
            else:
                return True
        except PermissionError as e:
            if attempt < retries -1:
                if attempt ==1:
                    try:
                        import gc
                        gc.collect()
                    except Exception as e_gc:
                        logger.error(f"Error during garbage collection: {e_gc}")
                current_delay *= backoff_factor
            else:
                if chat_id and bot:
                    await bot.send_message(
                            chat_id=chat_id,
                            text=f"⚠️ Could not delete temporary file after {retries} attempts: {os.path.basename(file_path)}\nError: {e}. You may need to manually delete it from the server."
                        )
        except Exception as e:
            if attempt == retries - 1 and chat_id and bot:
                
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ An unexpected error occurred deleting temporary file: {os.path.basename(file_path)}\nError: {e}. You may need to manually delete it."
                )
            return False
    return False         

def main():
    application= Application.builder().token(Bot_token).build()
    application.add_handler(CommandHandler('start',start))
    application.add_handler(CommandHandler('help',help))
    application.add_handler(MessageHandler(filters.Document.PDF,extract_data))
    application.add_handler(MessageHandler(filters.Document.IMAGE, extract_image_data)) 
    application.add_handler(MessageHandler(filters.PHOTO, extract_photo_data))
    
    application.add_handler(CallbackQueryHandler(button_callback))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edited_data))
    application.run_polling(allowed_updates=Update.ALL_TYPES)
if __name__ =="__main__":
    main()