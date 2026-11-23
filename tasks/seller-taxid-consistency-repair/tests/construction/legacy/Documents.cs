using System;
using System.Linq;

namespace SellerRegistration
{
    public static class Documents
    {
        public static string Digits(string value)
        {
            if (value == null) return null;
            var digits = new string(value.Where(char.IsDigit).ToArray());
            return digits.Length == 0 ? null : digits;
        }
        private static bool Check(string value, int[] weights)
        {
            var remainder = weights.Select((weight,index) => weight * (value[index]-'0')).Sum() % 11;
            return value[weights.Length]-'0' == (remainder < 2 ? 0 : 11-remainder);
        }
        public static bool Personal(string value)
        {
            value = Digits(value);
            return value == null || value.Length == 11 && value.Distinct().Count() > 1 && Check(value,new[]{10,9,8,7,6,5,4,3,2}) && Check(value,new[]{11,10,9,8,7,6,5,4,3,2});
        }
        public static bool Company(string value)
        {
            value = Digits(value);
            return value == null || value.Length == 14 && Check(value,new[]{5,4,3,2,9,8,7,6,5,4,3,2}) && Check(value,new[]{6,5,4,3,2,9,8,7,6,5,4,3,2});
        }
    }
}
