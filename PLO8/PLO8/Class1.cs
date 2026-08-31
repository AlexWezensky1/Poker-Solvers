namespace PLO8;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection.Metadata;
using System.Runtime.ExceptionServices;
using Microsoft.VisualBasic;
using static System.Text.Json.JsonSerializer;

public class PLO8
{
    public static void Main()
    {
        // Ctrl + / to un/comment blocks of lines
        Deck deck = new Deck();
        Console.Write("\nFilling shoe...");
        //int numberOfDecks = 1;
        //deck.FillDeck(numberOfDecks); // Fill the deck with 8 decks of cards
        deck.FillDeckHighToLow(); // Fill the deck with cards from high to low
        deck.PrintDeck();
        int numberOfHands = 1;
        //deck.Deal4Cards(numberOfHands);
        //deck.Deal6Cards(numberOfHands);
        deck.Deal9Cards(numberOfHands);

        // 52C6 20,358,520      8525 ms     8 sec
        // 52C7 133,784,560     1008360 ms  17 min
        // 52C8 752,538,150     
        // 52C9 3,679,075,400   
    }
}

public class Card
{
    public enum Suits
    {
        Diamonds, Hearts, Clubs, Spades
    }

    public int Value
    {
        get;
        set;
    }

    public Suits Suit
    {
        get;
        set;
    }

    public int DeckNumber
    {
        get;
        set;
    }

    //Used to get full name, also useful if you want to just get the named value
    public string NamedValue
    {
        get
        {
            string name = string.Empty;
            switch (Value)
            {
                case (14):
                    name = "A";
                    break;
                case (13):
                    name = "K";
                    break;
                case (12):
                    name = "Q";
                    break;
                case (11):
                    name = "J";
                    break;
                case (10):
                    name = "T";
                    break;
                default:
                    name = Value.ToString();
                    break;
            }

            return name;
        }
    }

    public string Name
    {
        get
        {
            return NamedValue + Suit.ToString().Substring(0, 1).ToLower();// + ", deck number " + DeckNumber;
        }
    }

    public Card(int Value, Suits Suit, int DeckNumber = 1)
    {
        this.Value = Value;
        this.Suit = Suit;
        this.DeckNumber = DeckNumber;
    }
    public Card()
    { }
}


public class Deck
{
    private List<Card> cards = new List<Card>();
    private List<Card> playerCards = new List<Card>();
    private Dictionary<List<Card>, string> AllOmahaHands = new Dictionary<List<Card>, string>() { };
    private List<List<Card>> AllOmahaHandsList = new List<List<Card>>();
    // private Random rng = new Random();
    // private List<Card> bankerCards = new List<Card>();
    // private bool playerThirdCardExists = false;
    // private bool bankerThirdCardExists = false;
    // private string listOfWinners = "";
    public void FillDeck(int NumberofDecks)
    {
        int totalCards = NumberofDecks * 52;
        //Can use a single loop utilising the mod operator % and Math.Floor
        //Using division based on 13 cards in a suit
        for (int i = 0; i < totalCards; i++)
        {
            Card.Suits suit = (Card.Suits)(Math.Floor((decimal)i / 13) % 4);
            //Add 2 to value as a cards start at 2
            int val = i % 13 + 2;
            int deckNumber = (int)Math.Floor((decimal)i / 52) + 1; // Calculate the deck number
            cards.Add(new Card(val, suit, deckNumber));
        }
    }
    public void FillDeckHighToLow()
    {
        //Can use a single loop utilising the mod operator % and Math.Floor
        //Using division based on 13 cards in a suit
        for (int i = 51; i >= 0; i--)
        {
            Card.Suits suit = (Card.Suits)(Math.Floor((decimal)i / 13) % 4);
            //Add 2 to value as a cards start at 2
            int val = i % 13 + 2;
            cards.Add(new Card(val, suit, 1));
        }
    }

    public void PrintDeck()
    {
        foreach (Card card in this.cards)
        {
            Console.WriteLine(card.Name);
        }
    }

    // public void ShuffleDeck()
    // {   //fisher-yates shuffle https://en.wikipedia.org/wiki/Fisher%E2%80%93Yates_shuffle
    //     for (int i = this.cards.Count - 1; i > 0; i--)
    //     {
    //         int j = rng.Next(0, i + 1);
    //         (this.cards[i], this.cards[j]) = (this.cards[j], this.cards[i]);
    //     }
    //     //listOfWinners = ""; //reset list of winners
    // }

    public void Deal4Cards(int numberOfHands)
    {
        var watch = System.Diagnostics.Stopwatch.StartNew();
        for (int i = 0; i < 52; i++)
        {
            for (int j = 1 + i; j < 52; j++)
            {
                for (int k = 1 + j; k < 52; k++)
                {
                    for (int l = 1 + k; l < 52; l++)
                    {
                        List<Card> hand = new List<Card>();
                        hand.Clear();
                        Card card = this.cards[i];
                        hand.Add(card);
                        Card card2 = this.cards[j];
                        hand.Add(card2);
                        Card card3 = this.cards[k];
                        hand.Add(card3);
                        Card card4 = this.cards[l];
                        hand.Add(card4);
                        //AllOmahaHands.Add(hand, "");
                        AllOmahaHandsList.Add(hand);
                    }
                }
            }
        }
        //PrintDict(AllOmahaHands);
        PrintAllOmahaHandsList();
        watch.Stop();
        var elapsedMs = watch.ElapsedMilliseconds;
        Console.WriteLine($"Elapsed time: {elapsedMs} ms");
    }

    public void Deal6Cards(int numberOfHands)
    {
        var watch = System.Diagnostics.Stopwatch.StartNew();
        for (int i = 0; i < 52; i++)
        {
            for (int j = 1 + i; j < 52; j++)
            {
                for (int k = 1 + j; k < 52; k++)
                {
                    for (int l = 1 + k; l < 52; l++)
                    {
                        for (int m = 1 + l; m < 52; m++)
                        {
                            for (int n = 1 + m; n < 52; n++)
                            {
                                List<Card> hand = new List<Card>();
                                hand.Clear();
                                Card card = this.cards[i];
                                hand.Add(card);
                                Card card2 = this.cards[j];
                                hand.Add(card2);
                                Card card3 = this.cards[k];
                                hand.Add(card3);
                                Card card4 = this.cards[l];
                                hand.Add(card4);
                                Card card5 = this.cards[m];
                                hand.Add(card5);
                                Card card6 = this.cards[n];
                                hand.Add(card6);
                                //AllOmahaHands.Add(hand, "");
                                AllOmahaHandsList.Add(hand);
                            }
                        }
                    }
                }
            }
        }
        //PrintDict(AllOmahaHands);
        PrintAllOmahaHandsList();
        watch.Stop();
        var elapsedMs = watch.ElapsedMilliseconds;
        Console.WriteLine($"Elapsed time: {elapsedMs} ms");
    }

    public void Deal9Cards(int numberOfHands)
    {
        var watch = System.Diagnostics.Stopwatch.StartNew();
        for (int i = 0; i < 52; i++)
        {
            for (int j = 1 + i; j < 52; j++)
            {
                for (int k = 1 + j; k < 52; k++)
                {
                    for (int l = 1 + k; l < 52; l++)
                    {
                        for (int m = 1 + l; m < 52; m++)
                        {
                            for (int n = 1 + m; n < 52; n++)
                            {
                                for (int o = 1 + n; o < 52; o++)
                                {
                                    for (int p = 1 + o; p < 52; p++)
                                    {
                                    //     for (int q = 1 + p; q < 52; q++)
                                    //     {
                                            List<Card> hand = new List<Card>();
                                            hand.Clear();
                                            Card card = this.cards[i];
                                            hand.Add(card);
                                            Card card2 = this.cards[j];
                                            hand.Add(card2);
                                            Card card3 = this.cards[k];
                                            hand.Add(card3);
                                            Card card4 = this.cards[l];
                                            hand.Add(card4);
                                            Card card5 = this.cards[m];
                                            hand.Add(card5);
                                            Card card6 = this.cards[n];
                                            hand.Add(card6);
                                            Card card7 = this.cards[o];
                                            hand.Add(card7);
                                            Card card8 = this.cards[p];
                                            hand.Add(card8);
                                            // Card card9 = this.cards[q];
                                            // hand.Add(card9);
                                            //AllOmahaHands.Add(hand, "");
                                            AllOmahaHandsList.Add(hand);
                                            
                                    //     }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        //PrintDict(AllOmahaHands);
        PrintAllOmahaHandsList();
        watch.Stop();
        var elapsedMs = watch.ElapsedMilliseconds;
        Console.WriteLine($"Elapsed time: {elapsedMs} ms");
    }

    public void PrintDict(Dictionary<List<Card>, string> dict)
    {
        foreach (var kvp in dict)
        {
            Console.WriteLine($"Key: {string.Join("", kvp.Key.Select(c => c.Name))}, Value: {kvp.Value}");
        }
    }
    public void PrintAllOmahaHandsList()
    {
        // foreach (var hand in AllOmahaHandsList)
        // {
        //     Console.WriteLine(string.Join("", hand.Select(c => c.Name)));
        // }
        Console.WriteLine($"Total Omaha Hands: {AllOmahaHandsList.Count}");
    }

    public void Deal(int i)
    {
        while (i > 0)
        {
            playerCards.Clear();
            // bankerCards.Clear();
            // playerThirdCardExists = false;
            // Deal two cards to each player
            Console.WriteLine("\n\nDealing cards...");
            playerCards.Add(Draw());
            Console.WriteLine($"Player receives: {playerCards[0].Name}");

            playerCards.Add(Draw());
            Console.WriteLine($"Player receives: {playerCards[1].Name}");

            // bankerCards.Add(Draw());
            // Console.WriteLine($"\nBanker receives: {bankerCards[0].Name}");

            // bankerCards.Add(Draw());
            // Console.WriteLine($"Banker receives: {bankerCards[1].Name}");
            i--;
        }
    }
    public Card Draw()
    {
        // CheckCutCard();
        Card card = this.cards[this.cards.Count - 1];
        this.cards.RemoveAt(this.cards.Count - 1);
        return card;
    }
    // public void DetemineWinnerAndSave(ref string listOfWinners)
    // {

    //     if (PlayerTotalBaccaratValue() > BankerTotalBaccaratValue())
    //     {
    //         Console.WriteLine("\nPlayer wins!");
    //         listOfWinners += "P";
    //     }
    //     else if (PlayerTotalBaccaratValue() < BankerTotalBaccaratValue())
    //     {
    //         Console.WriteLine("\nBanker wins!");
    //         listOfWinners += "B";
    //     }
    //     else
    //     {
    //         Console.WriteLine("\nIt's a tie!");
    //         listOfWinners += "T";
    //     }
    // }

    public void ExportToCSV()
    {
        using (StreamWriter sw = new StreamWriter("results.txt", false))
        {
            //sw.WriteLine(listOfWinners);
        }
        Console.WriteLine("File exported!");
    }
}