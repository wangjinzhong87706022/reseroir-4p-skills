import pymysql, json, os

conn = pymysql.connect(
    host=os.environ.get('SRM_DB_HOST', '127.0.0.1'),
    port=int(os.environ.get('SRM_DB_PORT', 3306)),
    user=os.environ.get('SRM_DB_USER', 'root'),
    password=os.environ.get('SRM_DB_PASSWORD', ''),
    database=os.environ.get('SRM_DB_NAME', 'powerelf_srm_yml'),
    charset='utf8mb4'
)
cursor = conn.cursor()

# master站码是3
stcd = '3'

# 查询最近24条水位记录
cursor.execute("""
    SELECT tm, rz, inq, otq, w 
    FROM st_rsvr_r 
    WHERE stcd = %s AND deleted = 0 
    ORDER BY tm DESC 
    LIMIT 24
""", (stcd,))
rows = cursor.fetchall()
print('Total recent records:', len(rows))
for r in rows:
    print(json.dumps({
        'tm': str(r[0]), 
        'rz': float(r[1]) if r[1] else None, 
        'inq': float(r[2]) if r[2] else None, 
        'otq': float(r[3]) if r[3] else None, 
        'w': float(r[4]) if r[4] else None
    }, ensure_ascii=False))

# 数据范围
cursor.execute("""
    SELECT MIN(tm), MAX(tm) 
    FROM st_rsvr_r 
    WHERE stcd = %s AND deleted = 0
""", (stcd,))
range_result = cursor.fetchone()
print('Data range:', str(range_result[0]), 'to', str(range_result[1]))

# 查看st_rsvr_r表结构
cursor.execute("DESCRIBE st_rsvr_r")
print("\nst_rsvr_r columns:")
for col in cursor.fetchall():
    print(" ", col)

cursor.close()
conn.close()
