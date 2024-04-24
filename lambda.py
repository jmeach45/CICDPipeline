import json
import boto3
from datetime import datetime
from hashlib import sha256
import random

# Initialize the DynamoDB client
dynamodb = boto3.client('dynamodb')

def lambda_handler(event, context):
    
    if 'body' in event and event['body'] is not None:
        body = json.loads(event['body'])
        merchant_name = body.get('merchant_name')
        token = body.get('merchant_token')
        bank = body.get('bank')
        cc_num = body.get('cc_num')
        card_type = body.get('card_type')
        security_code = body.get('security_code')
        amount = float(body.get('amount'))
        card_zip = body.get('card_zip')
        timestamp_str = body.get('timestamp')
    else:
        return {
            'statusCode': 400,
            'body': 'There was an error in the request, no body present.'
        }
    
    # Convert the timestamp string to a datetime object
    timestamp = datetime.fromisoformat(timestamp_str)
    
    # Check if the bank is available
    if random.random() < 0.1:  # 10% chance of bank not being available
        status = 'Error - Bank not available.'
    else:
        # Bank is available, proceed with transaction processing
        # Retrieve the Merchant table
        table_name = 'MerchantTable'
        
        # Query the table for the given merchant name and token
        response = dynamodb.query(
            TableName=table_name,
            KeyConditionExpression='#name = :name AND #token = :token',
            ExpressionAttributeNames={
                '#name': 'MerchantName',
                '#token': 'Token',
            },
            ExpressionAttributeValues={
                ':name': {'S': merchant_name},
                ':token': {'S': token},
            }
        )
        
        # Check if a matching merchant was found
        if response['Count'] == 1:
            # Determine if the card type is credit or debit
            if card_type.lower() == 'credit':
                # Query the Bank table for credit card information
                bank_response = dynamodb.get_item(
                    TableName='BankTable',
                    Key={
                        'BankName': {'S': bank},
                        'AccountNum': {'N': cc_num}
                    }
                )
                if 'Item' not in bank_response:
                    return {
                        'statusCode': 400,
                        'body': 'Error - Bad Bank or Account Number.'
                    }
                
                credit_limit = float(bank_response['Item'].get('CreditLimit', {'S': '0'}).get('S', '0'))
                credit_used_response = dynamodb.get_item(
                    TableName='BankTable',
                    Key={
                        'BankName': {'S': bank},
                        'AccountNum': {'N': cc_num}
                    },
                    ProjectionExpression='CreditUsed'
                )
                credit_used = float(credit_used_response['Item'].get('CreditUsed', {'S': '0'}).get('S', '0'))
                if amount > (credit_limit - credit_used):
                    status = 'Declined. Insufficient Funds.'
                else:
                    # Update the Bank table with the adjusted credit used
                    new_credit_used = credit_used + amount
                    dynamodb.update_item(
                        TableName='BankTable',
                        Key={
                            'BankName': {'S': bank},
                            'AccountNum': {'N': cc_num}
                        },
                        UpdateExpression='SET CreditUsed = :val',
                        ExpressionAttributeValues={
                            ':val': {'S': str(new_credit_used)}
                        }
                    )
                    status = 'Approved.'
            elif card_type.lower() == 'debit':
                # Query the Bank table for debit card information
                bank_response = dynamodb.get_item(
                    TableName='BankTable',
                    Key={
                        'BankName': {'S': bank},
                        'AccountNum': {'N': cc_num}
                    }
                )
                if 'Item' not in bank_response:
                    return {
                        'statusCode': 400,
                        'body': 'Error - Bad Bank or Account Number.'
                    }
                
                balance = float(bank_response['Item'].get('Balance', {'S': '0'}).get('S', '0'))
                if amount > balance:
                    status = 'Declined. Insufficient Funds.'
                else:
                    # Update the Bank table with the adjusted balance
                    new_balance = balance - amount
                    dynamodb.update_item(
                        TableName='BankTable',
                        Key={
                            'BankName': {'S': bank},
                            'AccountNum': {'N': cc_num}
                        },
                        UpdateExpression='SET Balance = :val',
                        ExpressionAttributeValues={
                            ':val': {'S': str(new_balance)}
                        }
                    )
                    status = 'Approved.'
            else:
                return {
                    'statusCode': 400,
                    'body': 'Error - Invalid card type.'
                }
            
            # Write the transaction to the TransactionTable
            response = dynamodb.put_item(
                TableName='TransactionTable',
                Item={
                    'TransactionID': {'N': str(int(timestamp.timestamp()))},
                    'MerchantName': {'S': merchant_name},
                    'MerchantID': {'S': token},
                    'Last4CC': {'S': cc_num[-4:]},
                    'Amount': {'N': str(amount)},
                    'Timestamp': {'S': timestamp_str},
                    'Status': {'S': status}
                }
            )
            
            # Check if the transaction was successfully written
            if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                # Respond with success message
                return {
                    'statusCode': 200,
                    'body': status
                }
            else:
                return {
                    'statusCode': 500,
                    'body': 'Error recording transaction.'
                }
        else:
            # Respond with an error message
            return {
                'statusCode': 401,
                'body': 'Merchant not authorized.'
            }
    
    # Bank not available response
    return {
        'statusCode': 503,
        'body': 'Bank not available.'
    }



