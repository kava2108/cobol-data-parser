*> CUSTOMER RECORD LAYOUT - WORKING STORAGE SECTION
*> Demonstrates: group items, elementary items, OCCURS, REDEFINES, COMP-3
01 CUSTOMER-REC.
  05 CUST-HEADER.
    10 CUST-ID           PIC 9(5).
    10 CUST-TYPE         PIC X(1).
       88 RETAIL         VALUE 'R'.
       88 WHOLESALE      VALUE 'W'.
    10 CUST-STATUS       PIC 9(2) COMP-3.
  05 CUST-NAME.
    10 FIRST-NAME        PIC X(15).
    10 LAST-NAME         PIC X(20).
  05 CUST-ADDRESS.
    10 STREET            PIC X(30).
    10 CITY              PIC X(20).
    10 STATE             PIC X(2).
    10 ZIP-CODE          PIC 9(5).
    10 ZIP-ALT REDEFINES ZIP-CODE PIC X(5).
  05 CUST-FINANCE.
    10 BALANCE           PIC S9(9)V99 COMP-3.
    10 CREDIT-LIMIT      PIC S9(7)V99.
    10 LAST-PAYMENT-DATE PIC 9(8).
  05 ORDER-LINES OCCURS 10 TIMES.
    10 ORDER-ID          PIC 9(7).
    10 ORDER-AMT         PIC S9(7)V99 COMP-3.
  05 FILLER              PIC X(10).
