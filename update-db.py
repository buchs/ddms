from imports import *   # make sure these are at root namespace
from constants import *   # ""

VERSION_KEYCOL = 'database_version'

def make_query(textual_sql):
    try:
        sqlcommand = sqltext(textual_sql)
        return sqlcommand
    except Exception as exc:
        print('Error creating SQL query\n' + \
              f'{str(exc)}\n{str(sqlcommand)}')
        return None

def stmp_db_version(new_version):
    """
        update the database version. In this code, version is an integer, but it is stored as a string.
        first time is an insert.
    """
    if new_version == 1:  # adding k-v for the first time
        ins = tb_mdata.insert().values(keycol=VERSION_KEYCOL, valcol=str(new_version))
        result = db_conn.execute(ins)
        if result.rowcount != 1:
            print('stmp_db_version - trouble inserting into db')
            sys.exit(1)
    else:
        result = sqlupdate(tb_mdata).where(tb_mdata.c.keycol==VERSION_KEYCOL).values(valcol=str(new_version))
        if result.rowcount != 1:
            print('stmp_db_version - trouble updating db')
            sys.exit(1)

def get_db_version():
    # select valcol from mdata where keycol = VERSION_KEYCOL;
    sel = sqlselect([tb_mdata.c.valcol, ]).where(tb_mdata.c.keycol == VERSION_KEYCOL)
    result = db_conn.execute(sel)
    row = result.fetchone()
    return int(row[0])  # stored as string, but in this code used as integer

def make_backup():
    datestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    name = DATABASE_PATH.name
    backup_path = DATABASE_PATH.with_name(f'{name}.{datestamp}.bak')
    shutil.copyfile(DATABASE_PATH, backup_path)
    print(f'made backup of database to {backup_path}')

def main():
    global tb_mdata, db_conn

    if not DATABASE_PATH.exists():
        print('no existing database found. I do not think this is the program you think it is.')
        return

    mdata_table = 'mdata'

    db_connection_string = 'sqlite+pysqlite:///' + str(DATABASE_PATH)
    db_engine = create_engine(db_connection_string)
    db_conn = db_engine.connect()
    metadata = MetaData()

    # tb_items = Table('items', metadata,
    #                       Column('dir', String, index=True),
    #                       Column('path', String, primary_key=True, index=True),
    #                       Column('shahash', String, index=True),
    #                       Column('thumb', String),
    #                       Column('labels', String),
    #                       Column('bibleref', String, index=True))

    tb_mdata = Table(mdata_table, metadata,
                          Column('keycol', String, primary_key=True, index=True),
                          Column('valcol', String))

    # Now we have sections that do version updates from version to version + 1
    # Each section does one of these and then returns True, so this is a big case/select statement.
    # -- Version 0 --
    textual_sql = f"SELECT name FROM sqlite_master WHERE type = 'table' AND name = '{mdata_table}'"
    sqlcommand = make_query(textual_sql)
    row = db_conn.execute(sqlcommand).fetchone()
    if row is None:
        # table doesn't exist - so version is 0. Create the table
        # do tasks to bring us up to version 1.
        version = 0
        make_backup()
        metadata.create_all(db_engine) # create new mdata table
        # need to add a table column
        textual_sql = "ALTER TABLE items ADD 'bibleref';"
        sqlcommand = make_query(textual_sql)
        results = db_conn.execute(sqlcommand)
        if results.rowcount != -1:
            print('could not alter table')
            sys.exit(1)
        stmp_db_version(version+1)
        print('database updated from version 0 to 1')
        return True

    # else, we have a version number
    version = get_db_version()
    print(f'database version {version}')
    if version == 1:
        # make_backup() in each section
        print('no additional database updates to apply')
    else:
        print(f'what is this db version we found {version}?')

if __name__ == '__main__':
    main()
