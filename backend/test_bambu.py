import bambulabs_api as bl

p = bl.Printer("192.168.33.140", "ce20f16f", "00M09D491000919")
p.connect()
print("Connected OK")
p.disconnect()