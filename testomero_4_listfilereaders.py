from omero.gateway import BlitzGateway

HOST = "100.111.214.77"
PORT = 4064
USERNAME = "root"
PASSWORD = "omero"

conn = BlitzGateway(USERNAME, PASSWORD, host=HOST, port=PORT, secure=True)
if not conn.connect():
    raise RuntimeError("Could not connect to OMERO")

sf = conn.getServiceFactory()
# The ImporterConfig is accessible via the raw API
importer = sf.createRawFileStore()  # just to ensure connection
raw = conn.c.sf.getQueryService()

# List all registered readers
q = "select r from ome.model.core.Format r"
print("Trying to query available readers...")

try:
    readers = conn.getSession().getComponents()  # all installed components
    found = [c for c in readers if "OMEZarrReader" in c]
    if found:
        print("✅ OMEZarrReader is installed:", found)
    else:
        print("❌ OMEZarrReader not found in registered components")
except Exception as e:
    print("Could not query components:", e)

conn.close()
